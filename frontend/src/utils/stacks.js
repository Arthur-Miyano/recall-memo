// 技术栈多选工具：URL 查询参数解析与展示标签。
// 首页抽屉多选后以逗号拼接进 URL（stacks=python,agent）；兼容旧的单值 stack 参数。
export function parseStacksQuery(query) {
  if (typeof query.stacks === 'string' && query.stacks) return query.stacks.split(',').filter(Boolean)
  if (typeof query.stack === 'string' && query.stack) return [query.stack]
  return []
}

// 展示标签：空或只含 mixed（混合，不限栈）→ 回退值或 'MIXED'；否则大写拼接（PYTHON+AGENT）
export function stackLabel(stacks, fallback) {
  const list = (stacks || []).filter(s => s && s !== 'mixed')
  if (list.length) return list.join('+').toUpperCase()
  return (fallback || 'mixed').toUpperCase()
}
