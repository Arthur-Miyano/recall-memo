// 真实后端接口封装：baseURL 指向本地 FastAPI，统一错误处理
// 各视图用法：try { 真实数据 } catch { console.warn + 回退 mock } —— 页面永远不白屏
const BASE_URL = 'http://localhost:8000'

async function request(path, { method = 'GET', body } = {}) {
  const resp = await fetch(BASE_URL + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!resp.ok) {
    let detail = resp.statusText
    try { detail = (await resp.json()).detail || detail } catch { /* 非 JSON 错误体 */ }
    throw new Error(`${method} ${path} 失败（${resp.status}）：${detail}`)
  }
  return resp.json()
}

/* ---------- 首页 / 题库 / 设置 / 助理 ---------- */
export const getHomeSummary = () => request('/api/home/summary')
export const getBankOverview = () => request('/api/bank/overview')
export const postBankFocus = (stack, group, focused) =>
  request('/api/bank/focus', { method: 'POST', body: { stack, group, focused } })
export const getLlmSettings = () => request('/api/settings/llm')
export const postLlmSettings = (payload) =>
  request('/api/settings/llm', { method: 'POST', body: payload })
export const assistantChat = (payload) =>
  request('/api/assistant/chat', { method: 'POST', body: payload })

/* ---------- 会话流程（记忆训练 / 面试 / 回忆） ---------- */
export const createSession = (mode, stack, count) =>
  request('/api/sessions', { method: 'POST', body: { mode, stack, count } })
export const startQuiz = (sessionId) =>
  request(`/api/sessions/${sessionId}/start_quiz`, { method: 'POST' })
export const getCurrent = (sessionId) => request(`/api/sessions/${sessionId}/current`)
export const submitAnswer = (sessionId, answer, startedAt) =>
  request(`/api/sessions/${sessionId}/answer`, {
    method: 'POST',
    body: { answer, started_at: startedAt },
  })
export const skipQuestion = (sessionId) =>
  request(`/api/sessions/${sessionId}/skip`, { method: 'POST' })
export const getReview = (sessionId) => request(`/api/sessions/${sessionId}/review`)
export const getLatestReview = () => request('/api/sessions/latest-review')
export const getRetryQueue = () => request('/api/sessions/retry-queue')

/* ---------- 仪表盘统计 ---------- */
export const getStatsOverview = () => request('/api/stats/overview')
export const getStatsDaily = (days = 7) => request(`/api/stats/daily?days=${days}`)
