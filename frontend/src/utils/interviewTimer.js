export function interviewSeconds({ startedAt, askedAt, now, currentSeconds, totalSeconds }) {
  if (startedAt) return currentSeconds
  if (askedAt) {
    const elapsed = (now - new Date(askedAt).getTime()) / 1000
    return Math.max(0, Math.round(totalSeconds - elapsed))
  }
  return Math.max(0, currentSeconds - 1)
}

export function interviewTimedOut({ startedAt, seconds }) {
  return !startedAt && seconds <= 0
}
