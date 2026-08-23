import test from 'node:test'
import assert from 'node:assert/strict'

import { shouldRetry, retryDelay } from './retryPolicy.js'

const netErr = { isNetwork: true }

test('GET 网络错误可重试，次数用完后停止', () => {
  assert.equal(shouldRetry({ method: 'GET', error: netErr, attempt: 0, maxRetries: 2 }), true)
  assert.equal(shouldRetry({ method: 'GET', error: netErr, attempt: 2, maxRetries: 2 }), false)
})

test('声明幂等的写操作网络错误可重试', () => {
  assert.equal(shouldRetry({ method: 'POST', idempotent: true, error: netErr, attempt: 0, maxRetries: 1 }), true)
})

test('非幂等写操作不重试（防止重复提交）', () => {
  assert.equal(shouldRetry({ method: 'POST', error: netErr, attempt: 0, maxRetries: 3 }), false)
})

test('业务错误（4xx/5xx）与默认不重试', () => {
  assert.equal(shouldRetry({ method: 'GET', error: { status: 500 }, attempt: 0, maxRetries: 2 }), false)
  assert.equal(shouldRetry({ method: 'GET', error: netErr, attempt: 0 }), false)
})

test('退避：300 起倍增，封顶 1500', () => {
  assert.equal(retryDelay(0), 300)
  assert.equal(retryDelay(1), 600)
  assert.equal(retryDelay(10), 1500)
})
