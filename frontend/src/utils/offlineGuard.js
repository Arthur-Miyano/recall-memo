// 离线只读判定：全局 offline（api/index.js）置位期间，真实会话的写操作一律禁用 + 入口短路
// useMock 演示路径不发网络请求，不受离线影响（调用方先行分支走本地模拟，不进本判定）
// busy 兼容字符串（'出题中…'）与布尔：非空即视为进行中
export const OFFLINE_WRITE_TIP = '离线中，恢复连接后再试'

export function canSubmit({ offline, useMock, busy } = {}) {
  if (offline && !useMock) return false
  return !busy
}
