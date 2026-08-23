// 真实后端接口封装：baseURL 指向本地 FastAPI，统一错误处理
// 各视图用法：try { 真实数据 } catch { console.warn + 回退 mock } —— 页面永远不白屏
import { ref } from 'vue'

// 相对路径：开发模式走 vite proxy（/api → localhost:8000），生产模式由 FastAPI 同源托管
const BASE_URL = ''

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

// 幂等键生成：一次提交生成一个键，失败重试必须复用同键（后端 workflow_operations 凭此去重/重放结果）
export const newIdempotencyKey = () =>
  globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`

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
    let code
    try {
      const body = await resp.json()
      // 两种错误形态：{detail: 字符串或 {code, message}}（业务 4xx/409）、
      // {error: {code, message}, request_id}（LLM 错误边界，见后端 main.py）
      const d = body.detail
      if (typeof d === 'string') detail = d
      else if (d) { detail = d.message || JSON.stringify(d); code = d.code }
      else if (body.error) { detail = body.error.message || detail; code = body.error.code }
    } catch { /* 非 JSON 错误体 */ }
    const err = new Error(`${method} ${path} 失败（${resp.status}）：${detail}`)
    if (code) err.code = code // 稳定机器错误码（OPERATION_IN_PROGRESS / ANSWER_ALREADY_SUBMITTED / LLM_* 等）
    throw err
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
export const deleteBankQuestion = (id) =>
  request(`/api/bank/questions/${id}`, { method: 'DELETE' })
export const getLlmSettings = () => request('/api/settings/llm')
export const postLlmSettings = (payload) =>
  request('/api/settings/llm', { method: 'POST', body: payload })
// 数据备份与迁移：导出走浏览器直接下载（a 标签 href），导入走 multipart 上传
export const importDatabase = (formData) => requestForm('/api/settings/import-db', formData)
export const assistantChat = (payload) =>
  request('/api/assistant/chat', { method: 'POST', body: payload })
export const getAssistantHistory = (limit = 50, sessionId = null) =>
  request(`/api/assistant/history?limit=${limit}${sessionId != null ? `&session_id=${sessionId}` : ''}`)
export const getAssistantSessions = () => request('/api/assistant/sessions')
export const createAssistantSession = () =>
  request('/api/assistant/sessions', { method: 'POST' })
export const deleteAssistantSession = (id) =>
  request(`/api/assistant/sessions/${id}`, { method: 'DELETE' })

/* ---------- 笔记 ---------- */
export const getNotes = () => request('/api/notes')
export const createNote = (title = '未命名笔记') =>
  request('/api/notes', { method: 'POST', body: { title } })
export const getNote = (id) => request(`/api/notes/${id}`)
export const updateNote = (id, payload) =>
  request(`/api/notes/${id}`, { method: 'PUT', body: payload })
export const deleteNote = (id) => request(`/api/notes/${id}`, { method: 'DELETE' })
export const appendNote = (id, text, source = '') =>
  request(`/api/notes/${id}/append`, { method: 'POST', body: { text, source } })

/* ---------- 会话流程（记忆训练 / 面试 / 回忆） ---------- */
export const createSession = (mode, stack, count) =>
  request('/api/sessions', { method: 'POST', body: { mode, stack, count } })
export const startQuiz = (sessionId) =>
  request(`/api/sessions/${sessionId}/start_quiz`, { method: 'POST' })
export const getCurrent = (sessionId) => request(`/api/sessions/${sessionId}/current`)
export const submitAnswer = (sessionId, answer, startedAt, idempotencyKey) =>
  request(`/api/sessions/${sessionId}/answer`, {
    method: 'POST',
    body: { answer, started_at: startedAt, idempotency_key: idempotencyKey },
  })
export const skipQuestion = (sessionId, idempotencyKey) =>
  request(`/api/sessions/${sessionId}/skip`, {
    method: 'POST',
    body: idempotencyKey ? { idempotency_key: idempotencyKey } : undefined,
  })
export const getReview = (sessionId) => request(`/api/sessions/${sessionId}/review`)
export const getLatestReview = () => request('/api/sessions/latest-review')
export const getRetryQueue = () => request('/api/sessions/retry-queue')

/* ---------- 仪表盘统计 ---------- */
export const getStatsOverview = () => request('/api/stats/overview')
export const getStatsDaily = (days = 7) => request(`/api/stats/daily?days=${days}`)
export const getLlmUsage = (days = 30) => request(`/api/stats/llm-usage?days=${days}`)
