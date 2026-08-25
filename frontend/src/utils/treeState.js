// 记忆树折叠状态（纯逻辑，node --test 可测）：
// 折叠集合只记「被收起」节点的路径 key（如 "0/2"），默认全部展开；
// 组件持有 Set 的响应式副本，每次切换整体换新集合触发视图更新

// 根到节点的下标路径 → 折叠 key
export function nodeKey(path) {
  return path.join('/')
}

export function isCollapsed(collapsed, key) {
  return collapsed.has(key)
}

// 切换某节点的折叠态：不改动原集合，返回新集合
export function toggleCollapsed(collapsed, key) {
  const next = new Set(collapsed)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  return next
}
