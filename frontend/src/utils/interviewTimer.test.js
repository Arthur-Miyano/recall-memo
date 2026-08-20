import test from 'node:test'
import assert from 'node:assert/strict'

import { interviewSeconds, interviewTimedOut } from './interviewTimer.js'

test('timer freezes and never reports timeout after the user starts answering', () => {
  const seconds = interviewSeconds({
    startedAt: '2026-08-20T10:01:00.000Z',
    askedAt: '2026-08-20T10:00:00.000Z',
    now: Date.parse('2026-08-20T10:05:00.000Z'),
    currentSeconds: 60,
    totalSeconds: 120,
  })
  assert.equal(seconds, 60)
  assert.equal(interviewTimedOut({ startedAt: '2026-08-20T10:01:00.000Z', seconds: 0 }), false)
})

test('timer reaches zero when no answer has started', () => {
  const seconds = interviewSeconds({
    startedAt: null,
    askedAt: '2026-08-20T10:00:00.000Z',
    now: Date.parse('2026-08-20T10:03:00.000Z'),
    currentSeconds: 120,
    totalSeconds: 120,
  })
  assert.equal(seconds, 0)
  assert.equal(interviewTimedOut({ startedAt: null, seconds }), true)
})
