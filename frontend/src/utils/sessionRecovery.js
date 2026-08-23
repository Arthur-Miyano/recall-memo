// 会话恢复决策（纯函数，§8.1）：服务端状态是唯一事实来源，本地快照只用于恢复未提交草稿
// 与后端状态机对齐：backend/domain/session_state.py
//   进行中：MEMORIZE_SHOW/MEMORIZE_QUIZ/REVIEW_SHOW/REVIEW_QUIZ/INTERVIEW_SELECT/INTERVIEW_ANSWER/INTERVIEW_SCORE
//   终态：  IDLE / INTERVIEW_REVIEW / EXPIRED（EXPIRED 为过期清理产物）

// 本地快照结构版本：结构变更时 +1，旧版本快照一律作废（restart）
export const SNAPSHOT_VERSION = 1

const ACTIVE_STATES = new Set([
  'MEMORIZE_SHOW', 'MEMORIZE_QUIZ', 'REVIEW_SHOW', 'REVIEW_QUIZ',
  'INTERVIEW_SELECT', 'INTERVIEW_ANSWER', 'INTERVIEW_SCORE',
])
const TERMINAL_STATES = new Set(['IDLE', 'INTERVIEW_REVIEW'])

// 进入训练/面试页时，快照 + 服务端查询结果 → 恢复动作：
//   restore  恢复快照（进度/题干以服务端为准，本地只保留未提交草稿）
//   offline  后端不可达：本地快照仅作展示兜底（demo/离线态，禁止写请求）
//   finished 服务端已到终态而本地未同步到（如提交响应丢失）：按终态恢复（面试 → 复盘页）
//   restart  快照失效（版本不符 / 服务端无此会话 / 已过期 / 模式冲突）：丢弃重建
export function decideRestore({ snapshot, serverInfo = null, serverError = null, expectedMode = null }) {
  if (!snapshot || snapshot.version !== SNAPSHOT_VERSION) return { action: 'restart' }
  if (serverError) {
    // 网络层失败（后端不可达）走离线兜底；404 等业务错误说明服务端会话不存在，快照作废
    return { action: serverError.isNetwork ? 'offline' : 'restart' }
  }
  if (!serverInfo) return { action: 'restart' }
  if (serverInfo.state === 'EXPIRED') return { action: 'restart' }
  // 本地快照与服务端模式不一致：冲突以服务端为准，丢弃本地快照
  if (expectedMode && serverInfo.mode !== expectedMode) return { action: 'restart' }
  if (ACTIVE_STATES.has(serverInfo.state)) return { action: 'restore' }
  if (TERMINAL_STATES.has(serverInfo.state)) {
    return snapshot.finished
      ? { action: 'restore' }  // 本地也已同步到完成态：原样恢复总结页
      : { action: 'finished', sessionId: serverInfo.session_id }
  }
  return { action: 'restart' }
}

// 草稿是否仍然有效：服务端当前题与本地快照记录的是同一题才保留草稿；
// 服务端已推进（提交成功但响应丢失）则草稿已被接收，以服务端为准丢弃本地草稿
export const draftStillValid = (serverQuestionId, snapshotQuestionId) =>
  snapshotQuestionId != null && serverQuestionId === snapshotQuestionId
