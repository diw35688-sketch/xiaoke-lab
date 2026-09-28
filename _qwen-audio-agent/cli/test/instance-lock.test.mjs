import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { acquireCliInstance } from '../src/instance-lock.mjs'

test('allows only one live CLI instance', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qwenaudio-cli-lock-'))
  const first = acquireCliInstance(directory, {
    pid: 101,
    token: 'first',
    killImpl: pid => {
      if (pid === 101) return
      throw Object.assign(new Error('missing'), { code: 'ESRCH' })
    },
  })

  assert.throws(
    () => acquireCliInstance(directory, {
      pid: 202,
      token: 'second',
      killImpl: pid => {
        if (pid === 101) return
        throw Object.assign(new Error('missing'), { code: 'ESRCH' })
      },
    }),
    /另一个 qwenaudio CLI 已在运行/,
  )

  first.release()
  const second = acquireCliInstance(directory, {
    pid: 202,
    token: 'second',
    killImpl: () => {},
  })
  second.release()
})

test('recovers a stale CLI lock without deleting a replacement lock', () => {
  const directory = mkdtempSync(join(tmpdir(), 'qwenaudio-cli-stale-'))
  const path = join(directory, 'cli.lock')
  writeFileSync(path, JSON.stringify({ pid: 99, token: 'stale' }))
  const lock = acquireCliInstance(directory, {
    pid: 303,
    token: 'current',
    killImpl: () => {
      throw Object.assign(new Error('missing'), { code: 'ESRCH' })
    },
  })
  assert.equal(JSON.parse(readFileSync(path, 'utf8')).token, 'current')

  writeFileSync(path, JSON.stringify({ pid: 404, token: 'replacement' }))
  lock.release()
  assert.equal(JSON.parse(readFileSync(path, 'utf8')).token, 'replacement')
})
