export class AgentError extends Error {
  constructor(message, { status = 0, body = '', protocol = '' } = {}) {
    super(message)
    this.name = 'AgentError'
    this.status = status
    this.body = body
    this.protocol = protocol
  }
}

export function requestSignal(signal, timeoutMs) {
  if (!timeoutMs) return signal
  const timeout = AbortSignal.timeout(timeoutMs)
  return signal ? AbortSignal.any([signal, timeout]) : timeout
}
