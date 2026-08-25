import test from 'node:test'
import assert from 'node:assert/strict'

import { createPinia, setActivePinia } from 'pinia'
import { createServer } from 'vite'

async function loadStore(t) {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  t.after(() => vite.close())
  const { useSessionStore } = await vite.ssrLoadModule('/src/stores/session.js')
  setActivePinia(createPinia())
  return useSessionStore()
}

test('真实且未完成的记忆快照可以继续', async (t) => {
  const store = await loadStore(t)
  store.memorize = { sessionId: 16, finished: false, useMock: false }
  assert.equal(store.canResumeMemorize, true)
})

test('完成态、mock 或缺少 sessionId 的快照不能继续', async (t) => {
  const store = await loadStore(t)
  for (const snapshot of [
    { sessionId: 16, finished: true, useMock: false },
    { sessionId: 16, finished: false, useMock: true },
    { sessionId: null, finished: false, useMock: false },
    null,
  ]) {
    store.memorize = snapshot
    assert.equal(store.canResumeMemorize, false)
  }
})
