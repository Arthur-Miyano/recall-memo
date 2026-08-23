import test from 'node:test'
import assert from 'node:assert/strict'

import { canSubmit, OFFLINE_WRITE_TIP } from './offlineGuard.js'

test('离线时真实会话禁止写操作', () => {
  assert.equal(canSubmit({ offline: true, useMock: false, busy: '' }), false)
  assert.equal(canSubmit({ offline: true, useMock: false, busy: false }), false)
})

test('离线时 mock 演示路径不受影响（不发网络请求）', () => {
  assert.equal(canSubmit({ offline: true, useMock: true, busy: '' }), true)
})

test('在线且空闲可写；进行中（busy）不可写', () => {
  assert.equal(canSubmit({ offline: false, useMock: false, busy: '' }), true)
  assert.equal(canSubmit({ offline: false, useMock: false, busy: '评分中…' }), false)
  assert.equal(canSubmit({ offline: false, useMock: false, busy: true }), false)
})

test('离线 + busy 仍不可写；提示语区分离线', () => {
  assert.equal(canSubmit({ offline: true, useMock: false, busy: '记录中…' }), false)
  assert.match(OFFLINE_WRITE_TIP, /离线/)
})
