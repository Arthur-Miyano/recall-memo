import test from 'node:test'
import assert from 'node:assert/strict'

import { SNAPSHOT_VERSION, decideRestore, draftStillValid, shouldResyncMemorize } from './sessionRecovery.js'

const snap = (over = {}) => ({ version: SNAPSHOT_VERSION, sessionId: 7, finished: false, ...over })

test('无快照或版本不符：restart 重建', () => {
  assert.equal(decideRestore({ snapshot: null }).action, 'restart')
  assert.equal(decideRestore({ snapshot: snap({ version: 999 }) }).action, 'restart')
})

test('服务端会话进行中：restore（进度以服务端为准，草稿来自本地）', () => {
  const d = decideRestore({
    snapshot: snap(),
    serverInfo: { session_id: 7, mode: 'memorize', state: 'MEMORIZE_QUIZ' },
    expectedMode: 'memorize',
  })
  assert.equal(d.action, 'restore')
})

test('后端不可达（网络错误）：offline 本地快照仅展示', () => {
  const d = decideRestore({ snapshot: snap(), serverError: { isNetwork: true } })
  assert.equal(d.action, 'offline')
})

test('服务端会话不存在（404 等业务错误）：restart', () => {
  const d = decideRestore({ snapshot: snap(), serverError: { status: 404 } })
  assert.equal(d.action, 'restart')
})

test('会话过期（EXPIRED）：restart 丢弃重建', () => {
  const d = decideRestore({
    snapshot: snap(),
    serverInfo: { session_id: 7, mode: 'memorize', state: 'EXPIRED' },
  })
  assert.equal(d.action, 'restart')
})

test('模式冲突（本地 memorize / 服务端 interview）：以服务端为准，restart', () => {
  const d = decideRestore({
    snapshot: snap(),
    serverInfo: { session_id: 7, mode: 'interview', state: 'INTERVIEW_ANSWER' },
    expectedMode: 'memorize',
  })
  assert.equal(d.action, 'restart')
})

test('服务端已到终态且本地已同步完成：restore 看总结', () => {
  const d = decideRestore({
    snapshot: snap({ finished: true }),
    serverInfo: { session_id: 7, mode: 'memorize', state: 'IDLE' },
    expectedMode: 'memorize',
  })
  assert.equal(d.action, 'restore')
})

test('服务端已完成而本地未收到响应：finished（面试据此跳复盘页，不重复提交）', () => {
  const d = decideRestore({
    snapshot: snap(),
    serverInfo: { session_id: 7, mode: 'interview', state: 'INTERVIEW_REVIEW' },
    expectedMode: 'interview',
  })
  assert.equal(d.action, 'finished')
  assert.equal(d.sessionId, 7)
})

test('未知状态：restart 兜底', () => {
  const d = decideRestore({
    snapshot: snap(),
    serverInfo: { session_id: 7, mode: 'memorize', state: 'WHATEVER' },
  })
  assert.equal(d.action, 'restart')
})

test('草稿有效性：同一题才保留，服务端已推进则丢弃', () => {
  assert.equal(draftStillValid(42, 42), true)
  assert.equal(draftStillValid(43, 42), false)
  assert.equal(draftStillValid(42, null), false)
})

test('服务端已进入考核态时，即使本地仍是展示态也要同步当前题', () => {
  const snapshot = snap({ quizzing: false, finished: false, useMock: false })
  assert.equal(shouldResyncMemorize({ snapshot, serverInfo: { state: 'MEMORIZE_QUIZ' } }), true)
  assert.equal(shouldResyncMemorize({ snapshot, serverInfo: { state: 'MEMORIZE_SHOW' } }), false)
})
