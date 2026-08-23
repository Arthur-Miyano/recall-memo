// 自动重试判定（纯函数，§8.3）：仅「网络层失败」且「明确可重试」的请求才自动重试
//   明确可重试 = GET（只读）或调用方声明幂等（带 idempotency_key 的写操作）
//   4xx/5xx 业务错误与主动取消（AbortError）永不重试
export function shouldRetry({ method = 'GET', idempotent = false, error, attempt = 0, maxRetries = 0 }) {
  if (attempt >= maxRetries) return false
  if (!error || !error.isNetwork) return false
  return method === 'GET' || idempotent
}

// 重试退避：300ms 起按 2 倍递增，封顶 1500ms（本地后端，退避仅为避开瞬时抖动）
export const retryDelay = (attempt) => Math.min(300 * 2 ** attempt, 1500)
