// 实验助手前台 MCP Server：统一工具入口。
//
// 启动时从 Python 后端 /internal/tool-definitions 拉取全部工具定义，
// 自动注册成 MCP 工具。Qwen Audio 和 DeepSeek 看到完全相同的工具列表，
// 调用同一个后端执行链路（/internal/tool-execute），行为完全一致。
//
// 新增工具只需在 Python 端加一个 @tool，MCP 自动注册，不需要改这边的代码。

// Node 18+ 内置 fetch (undici) 不读 NODE_TLS_REJECT_UNAUTHORIZED，
// 必须显式设置 dispatcher 才能接受自签名 HTTPS 证书。
import { setGlobalDispatcher, Agent } from 'undici'
setGlobalDispatcher(new Agent({ connect: { rejectUnauthorized: false } }))

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import { z } from 'zod'
import path from 'node:path'
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs'

// 内部接口共享密钥：与 Python 后端 web/.internal_token 对应。
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

// 自动探测后端协议：打包版用自签名 HTTPS，开发版用 HTTP。
// 不依赖环境变量传播（Python→网关→MCP 子进程可能丢失 env），
// 通过探测 /health 端点自动选择可用地址。
let LAB_BASE_URL = process.env.LAB_ASSISTANT_BASE_URL || ''

async function detectBaseUrl() {
  const candidates = [
    process.env.LAB_ASSISTANT_BASE_URL,
    'https://127.0.0.1:8000',
    'http://127.0.0.1:8000',
  ].filter(Boolean)
  for (const base of candidates) {
    try {
      const r = await fetch(`${base}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(3000),
      })
      if (r.ok) {
        console.error(`[lab-mcp] Backend detected at ${base}`)
        return base
      }
    } catch { /* try next candidate */ }
  }
  console.error('[lab-mcp] Backend not detected, falling back to http://127.0.0.1:8000')
  return 'http://127.0.0.1:8000'
}
const MEMORY_FILE = process.env.LAB_EXPERIMENT_MEMORY_FILE
  || path.resolve(process.cwd(), 'lab', 'experiment-memory.json')
const CURRENT_LAB_FILE = process.env.LAB_CURRENT_LAB_FILE
  || path.resolve(process.cwd(), 'current-lab-session-id.txt')

// ── 工具调用失败保护 ──

const toolFailures = new Map()

async function withToolGuard(toolName, execute) {
  try {
    const result = await execute()
    toolFailures.delete(toolName)
    return result
  } catch (error) {
    const failures = (toolFailures.get(toolName) || 0) + 1
    toolFailures.set(toolName, failures)
    if (failures >= 3) {
      return {
        isError: true,
        content: [{
          type: 'text',
          text: `工具 ${toolName} 已连续失败 ${failures} 次，暂时停用该工具。`,
        }],
      }
    }
    return {
      isError: true,
      content: [{
        type: 'text',
        text: `${error?.message || '工具执行失败'}（第 ${failures} 次失败）`,
      }],
    }
  }
}

function truncateText(text, max = 20000) {
  const value = String(text || '')
  return value.length > max ? value.slice(0, max) + '\n…[已截断]' : value
}

// ── HTTP 辅助 ──

async function fetchJson(urlPath, { timeoutMs = 5000 } = {}) {
  const response = await fetch(`${LAB_BASE_URL}${urlPath}`, {
    method: 'GET',
    headers: { 'Accept': 'application/json', 'X-Internal-Token': internalToken() },
    signal: AbortSignal.timeout(timeoutMs),
  })
  if (!response.ok) {
    throw new Error(`实验后台 HTTP ${response.status}`)
  }
  return response.json()
}

async function postJson(urlPath, payload, { timeoutMs = 60000 } = {}) {
  const response = await fetch(`${LAB_BASE_URL}${urlPath}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-Internal-Token': internalToken() },
    body: JSON.stringify(payload || {}),
    signal: AbortSignal.timeout(timeoutMs),
  })
  if (!response.ok) {
    let detail = `实验后台 HTTP ${response.status}`
    try {
      const body = await response.json()
      if (body.detail) detail = String(body.detail)
    } catch { /* keep HTTP status text */ }
    throw new Error(detail)
  }
  return response.json()
}

// ── 当前实验会话 ──

function currentLabSessionId() {
  try {
    return String(readFileSync(CURRENT_LAB_FILE, 'utf8') || '').trim()
  } catch {
    return ''
  }
}

// ── 实验记忆（本地文件）──

function readMemoryStore() {
  try { return JSON.parse(readFileSync(MEMORY_FILE, 'utf8')) }
  catch { return {} }
}

function writeMemoryStore(store) {
  mkdirSync(path.dirname(MEMORY_FILE), { recursive: true })
  writeFileSync(MEMORY_FILE, JSON.stringify(store, null, 2), 'utf8')
}

function memoryForCurrentLab() {
  const labId = currentLabSessionId()
  return { labId, items: readMemoryStore()[labId] || [] }
}

// ── JSON Schema → Zod 转换 ──
// MCP SDK 要求用 zod 定义参数 schema，但后端给的是 JSON Schema。
// 这里做最小转换——大部分情况下用 z.any() 即可，后端自己校验。

function jsonSchemaToZod(schema) {
  if (!schema || typeof schema !== 'object') {
    return z.record(z.any()).optional()
  }
  const props = schema.properties || {}
  const required = new Set(schema.required || [])
  const shape = {}
  for (const [key, def] of Object.entries(props)) {
    let field
    const t = def.type
    if (t === 'string') {
      field = z.string()
      if (def.description) field = field.describe(def.description)
    } else if (t === 'integer') {
      field = z.number().int()
      if (def.description) field = field.describe(def.description)
    } else if (t === 'number') {
      field = z.number()
      if (def.description) field = field.describe(def.description)
    } else if (t === 'boolean') {
      field = z.boolean()
    } else if (t === 'array') {
      field = z.array(z.any())
    } else if (t === 'object') {
      field = z.record(z.any())
    } else if (Array.isArray(t)) {
      // type: ["string", "null"] etc.
      if (t.includes('string')) field = z.string()
      else if (t.includes('integer')) field = z.number().int()
      else if (t.includes('number')) field = z.number()
      else field = z.any()
    } else {
      field = z.any()
    }
    if (def.enum) {
      field = z.enum(def.enum)
    }
    if (def.description && typeof field.describe === 'function') {
      field = field.describe(def.description)
    }
    if (!required.has(key)) {
      field = field.optional()
    }
    shape[key] = field
  }
  return z.object(shape)
}

// ── MCP Server ──

const server = new McpServer({
  name: 'lab-experiment',
  version: '2.0.0',
})

// ── 动态注册后端工具 ──

let registeredCount = 0

async function registerBackendTools() {
  console.error('[lab-mcp] Fetching tool definitions from backend...')
  const data = await fetchJson('/internal/tool-definitions', { timeoutMs: 5000 })
  const tools = data.tools || []
  console.error(`[lab-mcp] Got ${tools.length} tools from backend`)

  for (const tool of tools) {
    const zodSchema = jsonSchemaToZod(tool.parameters)
    server.registerTool(
      tool.name,
      { description: tool.description, inputSchema: zodSchema },
      async (args) => withToolGuard(tool.name, async () => {
        const labId = currentLabSessionId()
        const startedAt = Date.now()
        const result = await postJson('/internal/tool-execute', {
          tool_name: tool.name,
          arguments: args || {},
          lab_session_id: labId || undefined,
        })
        const elapsedMs = Date.now() - startedAt
        if (elapsedMs > 8000) {
          console.error(`[lab-mcp] SLOW: ${tool.name} took ${elapsedMs}ms`)
        }
        const ok = result.ok !== false
        const text = ok
          ? truncateText(JSON.stringify(result.result, null, 2))
          : `工具执行失败：${result.error || '未知错误'}`
        return {
          content: [{ type: 'text', text }],
        }
      }),
    )
    registeredCount++
  }
  console.error(`[lab-mcp] Registered ${registeredCount} tools`)
}

// ── 实验记忆工具（本地文件，不走后端）──

server.registerTool(
  'list_experiment_memory',
  {
    description: '列出当前实验独立记忆中的材料、计算、备注、摘要和画像。当用户问"这个实验用了哪些材料/之前的计算是多少/我记过什么"时调用。',
    inputSchema: z.object({}),
  },
  async () => withToolGuard('list_experiment_memory', async () => {
    const { labId, items } = memoryForCurrentLab()
    return {
      content: [{ type: 'text', text: truncateText(JSON.stringify({ labId, items }, null, 2)) }],
    }
  }),
)

server.registerTool(
  'save_experiment_memory',
  {
    description: '把当前实验的材料、计算、备注、阶段性摘要或用户画像保存到该实验独立的记忆中。kind 只能是 material/calculation/note/summary/profile。',
    inputSchema: z.object({
      kind: z.enum(['material', 'calculation', 'note', 'summary', 'profile']),
      name: z.string().optional(),
      content: z.string(),
    }),
  },
  async (args) => withToolGuard('save_experiment_memory', async () => {
    const kind = String(args?.kind || 'note')
    const name = String(args?.name || '').trim() || '未命名'
    const content = String(args?.content || '').trim()
    if (!content) throw new Error('content 不能为空')
    const { labId } = memoryForCurrentLab()
    if (!labId) throw new Error('当前没有实验会话，无法保存记忆')
    const store = readMemoryStore()
    const item = {
      id: `m-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      kind, name, content,
      created_at: new Date().toISOString(),
    }
    store[labId] = [...(store[labId] || []), item]
    writeMemoryStore(store)
    return {
      content: [{ type: 'text', text: JSON.stringify({ ok: true, labId, item }, null, 2) }],
    }
  }),
)

// ── 启动 ──

LAB_BASE_URL = await detectBaseUrl()
try {
  await registerBackendTools()
} catch (error) {
  console.error(`[lab-mcp] Failed to fetch tool definitions: ${error?.message || error}`)
  console.error('[lab-mcp] Starting with memory-only tools. Backend tools will be unavailable.')
}

const transport = new StdioServerTransport()
await server.connect(transport)
console.error('[lab-mcp] MCP server connected and ready.')
