import {
  closeSync,
  openSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs'
import { resolve } from 'node:path'
import { randomUUID } from 'node:crypto'

function processIsAlive(pid, killImpl) {
  if (!Number.isInteger(pid) || pid <= 0) return false
  try {
    killImpl(pid, 0)
    return true
  } catch (error) {
    return error?.code === 'EPERM'
  }
}

export function acquireCliInstance(
  configDirectory,
  {
    pid = process.pid,
    killImpl = process.kill,
    token = randomUUID(),
  } = {},
) {
  const path = resolve(configDirectory, 'cli.lock')
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const fd = openSync(path, 'wx', 0o600)
      writeFileSync(fd, JSON.stringify({ pid, token }), 'utf8')
      closeSync(fd)
      return {
        path,
        release() {
          try {
            const current = JSON.parse(readFileSync(path, 'utf8'))
            if (current.pid === pid && current.token === token) unlinkSync(path)
          } catch {
            // A missing or replaced lock no longer belongs to this process.
          }
        },
      }
    } catch (error) {
      if (error?.code !== 'EEXIST') throw error
      let existing
      try {
        existing = JSON.parse(readFileSync(path, 'utf8'))
      } catch {
        existing = null
      }
      if (processIsAlive(Number(existing?.pid), killImpl)) {
        throw new Error('另一个 qwenaudio CLI 已在运行')
      }
      try {
        unlinkSync(path)
      } catch (unlinkError) {
        if (unlinkError?.code !== 'ENOENT') throw unlinkError
      }
    }
  }
  throw new Error('无法获取 qwenaudio CLI 实例锁')
}
