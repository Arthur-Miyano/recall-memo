// 跨视图会话状态：面试结束后把 session_id 带给复盘页；记忆训练/面试快照跨页面保持（§8.1）
// 快照含本地快照版本与最后同步时间，并持久化到 localStorage（浏览器刷新也能恢复）；
// demo/mock 快照不持久化——演示数据不能在刷新后被当成用户数据（§8.2）。
// 恢复决策（是否有效/冲突/过期）见 utils/sessionRecovery.js，服务端状态是唯一事实来源。
import { defineStore } from 'pinia'
import { SNAPSHOT_VERSION } from '../utils/sessionRecovery'

const STORAGE_KEY = 'recall:session-snapshots'

// 读取持久化快照：版本不符或 demo 快照一律丢弃
function loadPersisted() {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY)
    if (!raw) return {}
    const data = JSON.parse(raw)
    const pick = (s) => (s && s.version === SNAPSHOT_VERSION && !s.useMock ? s : null)
    return { memorize: pick(data.memorize), interview: pick(data.interview) }
  } catch {
    return {}
  }
}

function persist(store) {
  try {
    // demo 快照落盘为 null：刷新后不会把 mock 当用户数据恢复
    const pick = (s) => (s && !s.useMock ? s : null)
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify({
      memorize: pick(store.memorize),
      interview: pick(store.interview),
    }))
  } catch { /* localStorage 不可用（隐私模式等）：降级为仅内存快照 */ }
}

// 打上版本与最后同步时间
const stamp = (snap) => ({ ...snap, version: SNAPSHOT_VERSION, syncedAt: new Date().toISOString() })

export const useSessionStore = defineStore('session', {
  state: () => ({
    // 最近一次完成（进入终局复盘）的面试会话 id
    lastReviewSessionId: null,
    // 记忆训练会话快照：开始训练后题目固定——切到别的页面再回来原样恢复；
    // 只有首页再次点「开始记忆」（带新 fresh token）才重开一轮抽题
    memorize: null,
    // 面试会话快照：同上；面试答完（或服务端已生成复盘）后清除
    interview: null,
    ...loadPersisted(),
  }),
  actions: {
    // 保存快照（自动盖版本/同步时间戳并持久化）；draft 字段即未提交的输入草稿
    saveMemorize(snap) { this.memorize = stamp(snap); persist(this) },
    saveInterview(snap) { this.interview = stamp(snap); persist(this) },
    clearMemorize() { this.memorize = null; persist(this) },
    clearInterview() { this.interview = null; persist(this) },
  },
})
