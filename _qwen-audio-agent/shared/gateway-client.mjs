export async function readGatewayHealth(baseUrl, fetchImpl = fetch) {
  try {
    const response = await fetchImpl(`${baseUrl}/api/health`, {
      signal: AbortSignal.timeout(1500),
    })
    const payload = await response.json()
    return payload && typeof payload === 'object' && payload.backend
      ? payload
      : null
  } catch {
    return null
  }
}
