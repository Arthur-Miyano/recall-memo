// 活跃 Agent 事件流：EventSource 订阅 /api/events（SSE），维护「当前活跃 Agent」响应式状态
// 断线由 EventSource 自带重连；每次收到事件刷新显示，静默 HIDE_AFTER_MS 后隐去
// 开发模式走 vite proxy（/api → localhost:8000），生产模式由 FastAPI 同源托管，与 api/index.js 一致
import { ref } from 'vue'

// 当前活跃事件：{agent, label, ts} | null；null 表示静默（无活跃 Agent 或已超时隐去）
export const activeAgentEvent = ref(null)

const HIDE_AFTER_MS = 4000

let es = null
let hideTimer = null

export function startAgentEvents() {
  if (es || typeof EventSource === 'undefined') return
  es = new EventSource('/api/events')
  es.onmessage = (e) => {
    try {
      activeAgentEvent.value = JSON.parse(e.data)
    } catch {
      return // 非 JSON 行（心跳注释等不会进 onmessage）：忽略
    }
    clearTimeout(hideTimer)
    hideTimer = setTimeout(() => { activeAgentEvent.value = null }, HIDE_AFTER_MS)
  }
  // onerror 无需处理：EventSource 自动重连；后端不可达时指示器保持静默即可
}
