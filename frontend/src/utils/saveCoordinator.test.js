import test from 'node:test'
import assert from 'node:assert/strict'

import { createSaveCoordinator } from './saveCoordinator.js'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

const tick = () => new Promise(resolve => setImmediate(resolve))

test('switch flush waits for the in-flight save and the newest queued edit', async () => {
  const first = deferred()
  const second = deferred()
  const calls = []
  const coordinator = createSaveCoordinator(async (noteId, payload) => {
    calls.push({ noteId, payload })
    return calls.length === 1 ? first.promise : second.promise
  })

  coordinator.markDirty(1, { content: 'first edit' })
  const autoSave = coordinator.flush()
  await tick()
  coordinator.markDirty(1, { content: 'latest edit' })

  let switchReady = false
  const beforeSwitch = coordinator.flush().then(result => {
    switchReady = true
    return result
  })

  assert.equal(calls.length, 1, 'only one PUT may be in flight')
  first.resolve({ id: 1, content: 'first edit' })
  await tick()
  assert.equal(calls.length, 2, 'the latest edit is saved after the first PUT')
  assert.equal(switchReady, false, 'switch must wait for the complete save chain')

  second.resolve({ id: 1, content: 'latest edit' })
  const result = await beforeSwitch
  await autoSave
  assert.equal(result.ok, true)
  assert.equal(result.saved.payload.content, 'latest edit')
  assert.equal(switchReady, true)
})

test('a failed save stops instead of retrying forever', async () => {
  let shouldFail = true
  let calls = 0
  const coordinator = createSaveCoordinator(async (noteId, payload) => {
    calls++
    if (shouldFail) throw new Error('offline')
    return { id: noteId, ...payload }
  })

  coordinator.markDirty(1, { content: 'draft' })
  const failed = await coordinator.flush()
  assert.equal(failed.ok, false)
  await new Promise(resolve => setTimeout(resolve, 20))
  assert.equal(calls, 1, 'failure must not schedule an immediate retry')
  assert.equal(coordinator.hasPending(), true)

  shouldFail = false
  coordinator.markDirty(1, { content: 'edited again' })
  const retried = await coordinator.flush()
  assert.equal(retried.ok, true)
  assert.equal(calls, 2, 'a later edit may explicitly trigger one new attempt')
})
