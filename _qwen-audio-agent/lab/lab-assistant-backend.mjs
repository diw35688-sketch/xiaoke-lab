// 实验助手后台 Adapter：把 QwenAudio 实时语音前台转来的任务
// 转发到本项目 FastAPI 的内部接口，由原 DeepSeek 实验助手执行。
import { defineBackendAdapter } from '../server/src/backend/backend-adapter-sdk.mjs'
import path from 'node:path'
import { existsSync, readFileSync } from 'node:fs'

const LAB_BASE_URL = process.env.LAB_ASSISTANT_BASE_URL || 'http://127.0.0.1:8000'
const CONVERSATION_FILE = process.env.LAB_CURRENT_CONVERSATION_FILE
  || path.resolve(process.cwd(), 'current-conversation-id.txt')
const LAB_SESSION_FILE = process.env.LAB_CURRENT_LAB_SESSION_FILE
  || path.resolve(process.cwd(), 'current-lab-session-id.txt')

// 内部接口共享密钥：与 Python 后端 web/.internal_token 对应。
// 探测多个候选路径，兼容从项目根或 _qwen-audio-agent 目录启动。
const INTERNAL_TOKEN_FILE = process.env.LAB_INTERNAL_TOKEN_FILE
  || [
    path.resolve(process.cwd(), 'web', '.internal_token'),
    path.resolve(process.cwd(), '..', 'web', '.internal_token'),
    path.resolve(process.cwd(), '.internal_token'),
  ].find((p) => existsSync(p))

function internalToken() {
  if (!INTERNAL_TOKEN_FILE) return ''
  try {
    return readFileSync(INTERNAL_TOKEN_FILE, 'utf8').trim()
  } catch {
    return ''
  }
}

function clean(value) {
  return String(value || '').trim()
}

function currentConversationFromFile() {
  try {
    return clean(readFileSync(CONVERSATION_FILE, 'utf8'))
  } catch {
    return ''
  }
}

function currentLabSessionFromFile() {
  try {
    return clean(readFileSync(LAB_SESSION_FILE, 'utf8'))
  } catch {
    return ''
  }
}

function cancellationError(taskId) {
  const error = new Error(`Task ${taskId} was cancelled`)
  error.code = 'WORK_CANCELLED'
  return error
}

export class LabAssistantBackendAdapter {
  constructor(options = {}) {
    this.labBaseUrl = clean(options.labBaseUrl || LAB_BASE_URL)
    this.ready = true
    this.closed = false
    this.active = new Map()
    this.listeners = new Set()
    this.conversationId = null
  }

  describe() {
    return {
      configured: true,
      enabled: true,
      protocol: 'lab-assistant-http',
      label: '实验助手后台（DeepSeek + 数据库/工具）',
      capabilities: {
        cancel: true,
        authorization: false,
      },
    }
  }

  async start() {
    if (this.closed) throw new Error('Lab assistant backend is closed')
    this.ready = true
    return { ok: true, status: 'ready' }
  }

  async health() {
    return {
      ok: this.ready && !this.closed,
      status: this.ready && !this.closed ? 'ready' : 'stopped',
    }
  }

  async submit(work) {
    const taskId = clean(work?.id)
    const ownerId = clean(work?.ownerId)
    const input = clean(
      work?.instruction
      || work?.objective
      || work?.originalRequest
      || work?.message,
    )
    if (!taskId || !ownerId || !input) {
      throw new Error('Lab assistant submit requires task id, owner and input')
    }
    await this.start()
    if (this.active.has(taskId)) {
      throw new Error(`Task ${taskId} is already active`)
    }
    const controller = new AbortController()
    const record = { taskId, ownerId, input, controller }
    this.active.set(taskId, record)
    this.emit({
      type: 'backend.activity',
      taskId,
      ownerId,
      activity: { kind: 'status', message: '已交给实验助手后台处理' },
    })
    try {
      let response = null
      let lastError = null
      // 每次提交都先读磁盘上的“当前会话/实验会话”文件；
      // 不能永久缓存旧的 conversationId，否则用户切换会话后语音后台仍写在旧会话里。
      const fileConversationId = currentConversationFromFile()
      const resolvedConversationId = fileConversationId || this.conversationId || undefined
      const resolvedLabSessionId = currentLabSessionFromFile() || undefined
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          response = await fetch(`${this.labBaseUrl}/internal/lab-voice-task`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Task-Id': taskId,
              'X-Internal-Token': internalToken(),
            },
            body: JSON.stringify({
              instruction: input,
              conversation_id: resolvedConversationId,
              lab_session_id: resolvedLabSessionId || undefined,
            }),
            signal: controller.signal,
          })
          if (response.ok) break
          let detail = `HTTP ${response.status}`
          try {
            const body = await response.json()
            if (body.detail) detail = String(body.detail)
          } catch {
            // ignore parse error, keep HTTP status text
          }
          lastError = new Error(`实验助手后台返回错误：${detail}`)
        } catch (error) {
          if (error.name === 'AbortError' || error.code === 'WORK_CANCELLED') {
            throw cancellationError(taskId)
          }
          lastError = error
        }
        if (attempt < 2) {
          await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)))
        }
      }
      if (!response?.ok) {
        throw lastError || new Error('实验助手后台未返回结果')
      }
      const data = await response.json()
      if (data.conversation_id) this.conversationId = data.conversation_id
      const content = clean(data.answer)
      if (!content) {
        throw new Error('实验助手后台没有返回可用结果')
      }
      return {
        content,
        artifacts: [],
      }
    } catch (error) {
      if (error.name === 'AbortError' || error.code === 'WORK_CANCELLED') {
        throw cancellationError(taskId)
      }
      console.error('lab-assistant-backend submit failed', taskId, error?.message || error)
      throw error
    } finally {
      this.active.delete(taskId)
    }
  }

  status(taskId, { ownerId } = {}) {
    const id = clean(taskId)
    if (!id) {
      return {
        ok: this.ready && !this.closed,
        status: this.ready && !this.closed ? 'ready' : 'stopped',
      }
    }
    const record = this.active.get(id)
    if (!record || (ownerId && clean(ownerId) !== record.ownerId)) {
      return { taskId: id, state: 'not_found' }
    }
    return {
      taskId: record.taskId,
      state: 'working',
      activity: [{ kind: 'status', message: '实验助手后台处理中' }],
    }
  }

  async cancel(taskId, { ownerId } = {}) {
    const record = this.active.get(clean(taskId))
    if (!record) return { taskId: clean(taskId), state: 'not_found' }
    if (ownerId && clean(ownerId) !== record.ownerId) {
      throw new Error('Cannot cancel work owned by another user')
    }
    record.controller.abort()
    return { taskId: record.taskId, state: 'cancelled' }
  }

  async respondAuthorization() {
    throw new Error('Lab assistant backend does not support authorization requests')
  }

  async respondInput() {
    throw new Error('Lab assistant backend does not support input requests')
  }

  subscribe(listener) {
    if (typeof listener !== 'function') {
      throw new TypeError('Backend event listener must be a function')
    }
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  emit(event) {
    for (const listener of this.listeners) {
      try {
        listener(event)
      } catch {
        // Observers cannot interrupt backend execution.
      }
    }
  }

  async close() {
    if (this.closed) return
    this.closed = true
    for (const record of this.active.values()) {
      record.controller.abort()
    }
    this.listeners.clear()
  }
}

export function createLabAssistantBackend(options) {
  return defineBackendAdapter(new LabAssistantBackendAdapter(options), {
    name: 'Lab assistant backend',
  })
}
