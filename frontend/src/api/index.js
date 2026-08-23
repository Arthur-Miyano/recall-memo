// 真实后端接口封装：baseURL 指向本地 FastAPI，统一错误处理（§8.3）
// 各视图用法：try { 真实数据 } catch { console.warn + 回退 mock } —— 页面永远不白屏
import { ref } from 'vue'
import { shouldRetry, retryDelay } from '../utils/retryPolicy'

// 相对路径：开发模式走 vite proxy（/api → localhost:8000），生产模式由 FastAPI 同源托管
const BASE_URL = ''

// 全局离线标记：仅「网络层失败 → 组件回退 mock 演示数据」时置位（App.vue 据此显示角标）
// 4xx/5xx 业务错误（如导入校验）不算离线；任意请求成功后自动清除
export const offline = ref(false)

// 统一错误对象（§8.3）：机器错误码 code / HTTP 状态 status / 网络层标记 isNetwork
// 4xx 业务错误（detail 字符串或 {code,message}）与 LLM 错误边界（{error:{code,message}}）都归一到此类
export class ApiError extends Error {
  constructor(message, { status, code, isNetwork = false } = {}) {
    super(message)
    this.name = 'ApiError'
    if (status !== undefined) this.status = status
    if (code) this.code = code // 稳定机器错误码（OPERATION_IN_PROGRESS / ANSWER_ALREADY_SUBMITTED / LLM_* 等）
    this.isNetwork = isNetwork
  }
}

// 默认超时 60s：评分/出题链路有 LLM 双调用，给足余量；上传/导入（requestForm）默认不限时
const DEFAULT_TIMEOUT = 60_000

// 网络层失败统一处理：置离线标记，isNetwork 供组件按需判断（离线回退 mock）
function networkError(method, path, cause) {
  offline.value = true
  return new ApiError(`${method} ${path} 网络错误（后端不可达）：${cause.message}`, { isNetwork: true })
}

// 幂等键生成：一次提交生成一个键，失败重试必须复用同键（后端 workflow_operations 凭此去重/重放结果）
export const newIdempotencyKey = () =>
  globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`

// 页面级请求域（§8.3）：组件 onUnmounted 时 cancel()，取消所有挂起请求
// 被取消的请求抛 AbortError，不置离线标记、不触发重试
export function createRequestScope() {
  const controller = new AbortController()
  return { signal: controller.signal, cancel: () => controller.abort() }
}

// 合并外部 signal（页面卸载取消）与超时：任一触发即中断 fetch
function combineSignals(timeout, signal) {
  const controller = new AbortController()
  const timer = timeout > 0
    ? setTimeout(() => controller.abort(new Error(`请求超时（${timeout}ms）`)), timeout)
    : null
  const onAbort = () => controller.abort(signal.reason)
  if (signal) {
    if (signal.aborted) onAbort()
    else signal.addEventListener('abort', onAbort, { once: true })
  }
  return {
    signal: controller.signal,
    isCancel: () => signal?.aborted === true,
    done: () => { if (timer) clearTimeout(timer); signal?.removeEventListener('abort', onAbort) },
  }
}

// 解析错误响应体：两种形态统一成 ApiError（detail: 字符串/{code,message}；或 {error:{code,message}}）
async function toApiError(resp, method, path) {
  let detail = resp.statusText
  let code
  try {
    const body = await resp.json()
    const d = body.detail
    if (typeof d === 'string') detail = d
    else if (d) { detail = d.message || JSON.stringify(d); code = d.code }
    else if (body.error) { detail = body.error.message || detail; code = body.error.code }
  } catch { /* 非 JSON 错误体 */ }
  return new ApiError(`${method} ${path} 失败（${resp.status}）：${detail}`, { status: resp.status, code })
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// method/body/timeout/signal/retry/responseType:
//   timeout      毫秒，0 表示不限时（requestForm 导入大库用）
//   signal       外部 AbortSignal（页面卸载取消，见 createRequestScope）
//   retry        自动重试次数：仅网络层失败且（GET 或 idempotent）才真正重试（§8.3，见 utils/retryPolicy）
//   idempotent   调用方声明本次写操作幂等（带 idempotency_key），允许自动重试
//   responseType 'blob' 时返回 Blob（文件下载）；默认解析 JSON；204 无内容返回 null
export async function request(
  path,
  { method = 'GET', body, timeout = DEFAULT_TIMEOUT, signal, retry = 0, idempotent = false, responseType } = {},
) {
  let attempt = 0
  for (;;) {
    const combined = combineSignals(timeout, signal)
    let resp
    try {
      resp = await fetch(BASE_URL + path, {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: combined.signal,
      })
    } catch (e) {
      combined.done()
      if (combined.isCancel()) throw e // 页面卸载的主动取消：原样抛出，不置离线、不重试
      const err = networkError(method, path, e)
      if (shouldRetry({ method, idempotent, error: err, attempt, maxRetries: retry })) {
        await sleep(retryDelay(attempt))
        attempt++
        continue
      }
      throw err
    }
    combined.done()
    if (!resp.ok) throw await toApiError(resp, method, path)
    offline.value = false // 后端恢复后下一次成功请求自动摘掉角标
    if (resp.status === 204) return null
    if (responseType === 'blob') return resp.blob()
    return resp.json()
  }
}

// multipart 版本（文件上传）：与 request 同款错误处理，但不设 Content-Type（浏览器自动生成 boundary）
// 导入整库合并耗时随库大小增长，默认不限时；支持 signal 取消
export async function requestForm(path, formData, { timeout = 0, signal } = {}) {
  const combined = combineSignals(timeout, signal)
  let resp
  try {
    resp = await fetch(BASE_URL + path, { method: 'POST', body: formData, signal: combined.signal })
  } catch (e) {
    combined.done()
    if (combined.isCancel()) throw e
    throw networkError('POST', path, e)
  }
  combined.done()
  if (!resp.ok) throw await toApiError(resp, 'POST', path)
  offline.value = false
  if (resp.status === 204) return null
  return resp.json()
}

/* ---------- 首页 / 题库 / 设置 / 助理 ---------- */
export const getHomeSummary = () => request('/api/home/summary')
export const getHealth = (opts) => request('/api/health', opts) // 离线恢复探测（App.vue 轮询用）
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
export const createSession = (mode, stack, count, opts) =>
  request('/api/sessions', { method: 'POST', body: { mode, stack, count }, ...opts })
export const getSessionInfo = (sessionId, opts) => request(`/api/sessions/${sessionId}`, opts)
export const startQuiz = (sessionId, opts) =>
  request(`/api/sessions/${sessionId}/start_quiz`, { method: 'POST', ...opts })
export const getCurrent = (sessionId, opts) => request(`/api/sessions/${sessionId}/current`, opts)
export const submitAnswer = (sessionId, answer, startedAt, idempotencyKey) =>
  request(`/api/sessions/${sessionId}/answer`, {
    method: 'POST',
    body: { answer, started_at: startedAt, idempotency_key: idempotencyKey },
    // 带幂等键的提交允许自动重试一次：网络抖动时重放返回已保存结果，不会重复记分
    idempotent: true,
    retry: 1,
  })
export const skipQuestion = (sessionId, idempotencyKey) =>
  request(`/api/sessions/${sessionId}/skip`, {
    method: 'POST',
    body: idempotencyKey ? { idempotency_key: idempotencyKey } : undefined,
    idempotent: true,
    retry: 1,
  })
export const getReview = (sessionId) => request(`/api/sessions/${sessionId}/review`)
export const getLatestReview = () => request('/api/sessions/latest-review')
export const getRetryQueue = () => request('/api/sessions/retry-queue')

/* ---------- 仪表盘统计 ---------- */
export const getStatsOverview = () => request('/api/stats/overview')
export const getStatsDaily = (days = 7) => request(`/api/stats/daily?days=${days}`)
export const getLlmUsage = (days = 30) => request(`/api/stats/llm-usage?days=${days}`)
