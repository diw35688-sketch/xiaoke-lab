// 实验助手里的 Qwen Audio 实时语音组件。
// 直接复用 qwen-audio-agent 的 useRealtimeVoice Hook（React），
// 不跳转外部页面，作为本应用内的一个功能挂载到 shell 视图。
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import useRealtimeVoice from '../web/src/useRealtimeVoice.js'

function qwenOrigin() {
  const host = window.location.hostname || '127.0.0.1'
  const lower = host.toLowerCase()
  const loopback = lower === 'localhost' || lower === '127.0.0.1' || lower === '[::1]' || lower === '::1'
  // 手机/公网/局域网 IP 访问时端口 3101 不一定可达，改走同源 /api/realtime 反向代理。
  if (!loopback) return ''
  const proto = window.location.protocol === 'https:' ? 'https:' : 'http:'
  return `${proto}//${host}:3101`
}

function newSessionId() {
  return 'lab-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10)
}

function upsertMessage(messages, event, role, final) {
  const id = event.responseId
    ? `voice:${event.responseId}`
    : event.turnId
      ? `user:${event.turnId}`
      : `${role}:${Date.now()}:${Math.random()}`
  const found = messages.findIndex(message => message.id === id)
  const next = { id, role, content: String(event.content || ''), final: false, interrupted: false }
  if (found >= 0) {
    const copy = messages.slice()
    copy[found] = {
      ...copy[found],
      content: copy[found].content + next.content,
      final: next.final || copy[found].final,
    }
    return copy
  }
  return [...messages, next]
}

function RealtimeWidget({ initialEnabled = false }) {
  const [sessionId, setSessionId] = useState(newSessionId)
  const [enabled, setEnabled] = useState(initialEnabled)
  const [connecting, setConnecting] = useState(false)
  const [messages, setMessages] = useState([])
  const [activity, setActivity] = useState('待命')
  const [statusText, setStatusText] = useState('')
  const onRealtimeEvent = useCallback(event => {
    if (event.type === 'turn.started') {
      setActivity('正在听你说')
    }
    if (event.type === 'voice.state' && event.state) {
      const labels = { idle: '待命', listening: '正在听你说', processing: '正在处理', speaking: '正在回复' }
      setActivity(labels[event.state] || String(event.state))
    }
    if (event.type === 'transcript.delta' && event.role === 'user') {
      setMessages(items => upsertMessage(items, event, 'user', false))
    }
    if (event.type === 'transcript.final' && event.role === 'user') {
      setMessages(items => upsertMessage(items, event, 'user', true))
      if (window.reportVoiceTranscript) {
        window.reportVoiceTranscript('user', String(event.content || ''), event.turnId)
      }
    }
    if (event.type === 'transcript.delta' && event.role === 'assistant') {
      setMessages(items => upsertMessage(items, event, 'assistant', false))
    }
    if (event.type === 'transcript.final' && event.role === 'assistant') {
      setMessages(items => upsertMessage(items, event, 'assistant', true))
      if (window.reportVoiceTranscript) {
        window.reportVoiceTranscript('assistant', String(event.content || ''), event.turnId)
      }
      setActivity('待命')
    }
    if (event.type === 'transcript.discard' && event.role === 'user' && event.turnId) {
      setMessages(items => items.filter(message => message.id !== `user:${event.turnId}`))
    }
    if (event.type === 'response.interrupted') {
      setMessages(items => items.map(message => (
        message.id === `voice:${event.responseId}`
          ? { ...message, interrupted: true, final: true }
          : message
      )))
      setActivity('已打断')
    }
    if (
      event.type === 'agent.activity'
      || (event.type && String(event.type).indexOf('task.') === 0)
      || (event.type && String(event.type).indexOf('backend.') === 0)
    ) {
      const activity = event.activity?.message
        || event.message
        || event.title
        || event.label
        || String(event.activity || event.type || '')
      if (activity) {
        setMessages(items => [
          ...items,
          {
            id: `activity:${Date.now()}:${Math.random()}`,
            role: 'system',
            content: String(activity),
            final: true,
          },
        ])
        try { window.dispatchEvent(new CustomEvent('lab:experiment-changed')); } catch (_) {}
      }
    }
    if (event.type === 'voice.connection') {
      setStatusText(event.state === 'connected' ? '' : (event.message || ''))
    }
    if (event.type === 'gateway.disconnected') {
      setStatusText('实时语音连接中断，正在重连')
    }
    if (event.type === 'voice.superseded') {
      // 另一台设备开启了实时语音，本机被自动接管：按钮关闭、不再自动重连。
      setEnabled(false)
      setConnecting(false)
      setStatusText('已在其他设备开启实时语音，本机已自动关闭')
    }
  }, [])

  const voice = useRealtimeVoice({
    sessionId,
    enabled,
    suspended: false,
    outputMuted: false,
    inputOnlyMute: true,
    wakeWordOnly: false,
    clientType: 'web',
    clientLabel: '实验助手·实时语音',
    clientStates: [],
    realtimeProvider: '',
    onEvent: onRealtimeEvent,
    onInputError: message => {
      setEnabled(false)
      setStatusText(String(message || '麦克风错误'))
    },
    onClientAction: () => {},
    onWakeWordAudio: () => {},
  })

  useEffect(() => {
    if (voice.error) setStatusText(voice.error)
    else if (enabled && !voice.inputReady) {
      setStatusText('正在请求麦克风权限…')
    } else if (enabled && voice.inputReady && voice.connectionState === 'connected') {
      setConnecting(false)
      if (statusText === '正在请求麦克风权限…' || statusText === '正在连接实时语音…') {
        setStatusText('')
      }
    } else if (voice.connectionState === 'connecting') {
      setStatusText('正在连接实时语音…')
    } else if (voice.connectionState === 'unavailable') {
      setConnecting(false)
      if (!statusText) setStatusText('连接中断，正在重连…')
    }
  }, [voice.error, voice.connectionState, enabled, voice.inputReady])

  useEffect(() => {
    const active = enabled && voice.inputReady
    try { localStorage.setItem('lab-qwen-realtime-enabled', active ? '1' : '0'); } catch (_) {}
    window.dispatchEvent(new CustomEvent('lab:realtime-voice-state', {
      detail: { enabled: active },
    }))
    if (!active && enabled) {
      try { window.dispatchEvent(new CustomEvent('lab:realtime-voice-error', {
        detail: {
          error: voice.error || String(voice.visualError || ''),
          connectionState: voice.connectionState,
          inputReady: voice.inputReady,
          enabled,
        },
      })); } catch (_) {}
    }
  }, [enabled, voice.inputReady])

  const start = () => {
    try { voice.activateAudio?.(); } catch (_) {}
    setConnecting(true)
    setEnabled(true)
    setStatusText('正在连接实时语音…')
  }
  const stop = () => {
    setConnecting(false)
    setEnabled(false)
    setStatusText('已关闭实时语音')
  }
  const resetSession = () => {
    setConnecting(false)
    setEnabled(false)
    setMessages([])
    setSessionId(newSessionId())
    setStatusText('')
    setActivity('待命')
  }

  const startRef = useRef(null)
  const stopRef = useRef(null)
  useEffect(() => {
    startRef.current = start
    stopRef.current = stop
    window.__labRealtimeStart = start
    window.__labRealtimeStop = stop
  })

  useEffect(() => {
    const handler = event => {
      const enabled = Boolean(event.detail?.enabled)
      if (enabled) startRef.current?.()
      else stopRef.current?.()
    }
    window.addEventListener('lab:realtime-voice-command', handler)
    return () => window.removeEventListener('lab:realtime-voice-command', handler)
  }, [])

  return (
    <div className="qwen-rw">
      <div className="qwen-rw-top">
        <button className={`sh-btn primary${enabled ? ' qwen-rw-active' : ''}`} type="button" disabled={connecting} onClick={() => (enabled ? stop() : start())}>
          {connecting ? '正在连接…' : enabled ? '关闭实时语音' : '开启实时语音'}
        </button>
        <button className="sh-btn" type="button" onClick={resetSession}>新会话</button>
        {enabled && !voice.inputReady ? (
          <button className="sh-btn" type="button" onClick={start}>重新授权麦克风</button>
        ) : null}
        <span className="qwen-rw-status">{enabled ? '● ' : ''}{activity || statusText || '待命'}</span>
      </div>
      <div className="qwen-rw-body">
        {!enabled ? (
          <div className="qwen-rw-empty">
            <div>🎙️</div>
            <p>点击“开启实时语音”开始全双工对话</p>
            <p className="qwen-rw-sub">可随时打断，语音由 DashScope Qwen Audio Realtime 提供</p>
          </div>
        ) : (
          <div className="qwen-rw-messages">
            {messages.length === 0 ? (
              <div className="qwen-rw-empty"><div>🎙️</div><p>正在聆听…</p></div>
            ) : messages.map(message => (
              <div key={message.id} className={`qwen-rw-msg ${message.role}`}>
                <div className="qwen-rw-bubble">
                  {message.content || '…'}
                  {message.interrupted ? <span className="qwen-rw-interrupted">（已打断）</span> : null}
                </div>
              </div>
            ))}
            <div className="qwen-rw-scroll-sentinel" />
          </div>
        )}
      </div>
      {statusText ? (
        <div className={statusText.indexOf('中断') >= 0 || statusText.indexOf('重连') >= 0 ? 'qwen-rw-info' : 'qwen-rw-error'}>
          {statusText}
        </div>
      ) : null}
    </div>
  )
}

export function mountQwenRealtime(container, options = {}) {
  window.__QWEN_AUDIO_ORIGIN__ = qwenOrigin()
  const root = createRoot(container)
  root.render(<RealtimeWidget initialEnabled={options.initialEnabled === true} />)
  return () => root.unmount()
}
