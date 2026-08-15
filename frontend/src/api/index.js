// 真实后端接口封装：baseURL 指向本地 FastAPI，统一错误处理
// 各视图用法：try { 真实数据 } catch { console.warn + 回退 mock } —— 页面永远不白屏
import { ref } from 'vue'

const BASE_URL = 'http://localhost:8000'

// 全局离线标记：仅「网络层失败 → 组件回退 mock 演示数据」时置位（App.vue 据此显示角标）
// 4xx/5xx 业务错误（如导入校验）不算离线；任意请求成功后自动清除
export const offline = ref(false)

// 网络层失败统一处理：置离线标记，错误对象带 isNetwork 供组件按需判断
function networkError(method, path, cause) {
  offline.value = true
  const err = new Error(`${method} ${path} 网络错误（后端不可达）：${cause.message}`)
  err.isNetwork = true
  return err
}

export async function request(path, { method = 'GET', body } = {}) {
  let resp
  try {
    resp = await fetch(BASE_URL + path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    throw networkError(method, path, e)
  }
  if (!resp.ok) {
    let detail = resp.statusText
    try { detail = (await resp.json()).detail || detail } catch { /* 非 JSON 错误体 */ }
    throw new Error(`${method} ${path} 失败（${resp.status}）：${detail}`)
  }
  offline.value = false // 后端恢复后下一次成功请求自动摘掉角标
  return resp.json()
}

// multipart 版本（文件上传）：与 request 同款错误处理，但不设 Content-Type（浏览器自动生成 boundary）
export async function requestForm(path, formData) {
  let resp
  try {
    resp = await fetch(BASE_URL + path, { method: 'POST', body: formData })
  } catch (e) {
    throw networkError('POST', path, e)
  }
  if (!resp.ok) {
    let detail = resp.statusText
    try { detail = (await resp.json()).detail || detail } catch { /* 非 JSON 错误体 */ }
    throw new Error(`POST ${path} 失败（${resp.status}）：${detail}`)
  }
  offline.value = false
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
export const getAssistantHistory = (limit = 50, sessionId = null) =>
  request(`/api/assistant/history?limit=${limit}${sessionId != null ? `&session_id=${sessionId}` : ''}`)
export const getAssistantSessions = () => request('/api/assistant/sessions')
export const createAssistantSession = () =>
  request('/api/assistant/sessions', { method: 'POST' })
export const deleteAssistantSession = (id) =>
  request(`/api/assistant/sessions/${id}`, { method: 'DELETE' })

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
