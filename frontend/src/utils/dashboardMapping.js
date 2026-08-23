// 仪表盘图表数据映射：接口数据 → 卡片/图表结构的纯函数
// 从 views/DashboardView.vue 抽出：无 DOM/Vue 依赖，便于 node --test 直测

// 本地日期 → 'YYYY-MM-DD'（与后端 daily 接口口径一致）
export function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// mock 兜底日历：把 28 个等级数字映射为最近 28 天的日期，统一为 InkCalendar 的 items 结构
export function mockCalItems(calendar, now = new Date()) {
  return calendar.map((v, i) => {
    const d = new Date(now)
    d.setDate(d.getDate() - (27 - i))
    return { date: fmtDate(d), total_count: v }
  })
}

// 小卡片方格条：最近 28 天（2 行 × 14 列），格内显示日号，今天印章红框
export function buildStrip28(calendar, now = new Date()) {
  const countMap = Object.fromEntries((calendar || []).map(c => [c.date, c.total_count]))
  const days = []
  for (let i = 27; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    const date = fmtDate(d)
    const count = countMap[date] || 0
    days.push({
      date,
      dayNum: d.getDate(),
      label: `${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`,
      level: Math.min(count, 4),
      isToday: i === 0,
      tip: `${d.getMonth() + 1}月${d.getDate()}日 · ${count} 题`,
    })
  }
  return days
}

// 连续打卡：从今天往前数有答题的天数（daily7 按日期升序）
export function countStreak(items) {
  let streak = 0
  for (let i = items.length - 1; i >= 0; i--) {
    if (items[i].total_count > 0) streak++
    else break
  }
  return streak
}

export const WEEKDAYS_CN = ['日', '一', '二', '三', '四', '五', '六']
// cell.status → 图谱节点状态
export const CELL2NODE = { done: 'mastered', weak: 'weak', todo: 'todo' }
// 逐题明细排序：未背的排最后
export const STATUS_ORDER = { weak: 0, done: 1, todo: 2 }
export const STATUS_CN = { done: '掌握', weak: '薄弱', todo: '未背' }
// 同知识点多题时的序号角标（①~⑳，超出兜底 ·n）
export const CIRCLED = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩','⑪','⑫','⑬','⑭','⑮','⑯','⑰','⑱','⑲','⑳']

// 图谱节点主标签：知识点（分组名），>8 字截断加 …；同知识点多题加圈号序号
export function kgLabel(groupName, idx, count) {
  const base = groupName.length > 8 ? groupName.slice(0, 8) + '…' : groupName
  if (count <= 1) return base
  return `${base} ${idx <= 20 ? CIRCLED[idx - 1] : '·' + idx}`
}

// 知识图谱小卡片（概览态）：不画节点图，每栈只统计 掌握/薄弱/未背 计数 + 完成比例
export function buildStackOverview(bank) {
  return (bank.stacks || []).map(s => {
    let done = 0, weak = 0, todo = 0
    s.groups.forEach(g => g.cells.forEach(c => {
      if (c.status === 'done') done++
      else if (c.status === 'weak') weak++
      else todo++
    }))
    const total = s.total || done + weak + todo
    return { key: s.key || s.name, label: s.name.toUpperCase(), done, weak, todo, total }
  })
}

// 今日建议：薄弱（待补答/低分）优先，取前 3
export function buildSuggestions(bank) {
  const weak = []
  bank.stacks.forEach(s => s.groups.forEach(g => g.cells.forEach(c => {
    if (c.status === 'weak') {
      weak.push({
        d: c.retry ? '待补答' : '低分',
        t: c.tip.split(' · ')[0],
        s: c.score == null ? '—' : String(c.score),
      })
    }
  })))
  weak.sort((a, b) => Number(a.s) - Number(b.s))
  return weak.slice(0, 3)
}

// 通用柱条换算：items → 等宽柱（key 为数值字段），柱高 ∝ 数值
export function makeBars(items, key, W, H, pad, bw) {
  if (!items.length) return { bars: [], max: 0 }
  const max = Math.max(...items.map(d => d[key]), 1e-9)
  const slot = (W - pad * 2) / items.length
  return {
    max,
    bars: items.map((d, i) => ({
      x: pad + i * slot + (slot - bw) / 2,
      y: H - pad - (d[key] / max) * (H - pad * 2),
      h: (d[key] / max) * (H - pad * 2),
      v: d[key], date: d.date, i,
    })),
  }
}

// 数值格式化：千分位整数 / 大额缩写（1.2k / 3.4M）
export const fmtInt = n => Number(n || 0).toLocaleString('en-US')
export const fmtBig = v => (v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(1) + 'k' : String(Math.round(v * 100) / 100))

// SVG 手绘坐标换算：slots = 满槽数据点数 - 1（7 天趋势 6，30 天趋势 29；与数据条数解耦）
export const axisX = (i, W, pad, slots) => pad + i * (W - pad * 2) / slots
export const axisY = (v, max, H, pad) => H - pad - v * (H - pad * 2) / max

// 阶梯折线：先水平后垂直的直角转折
export function stepPath(vals, max, W, H, pad, slots) {
  if (!vals.length) return ''
  let d = `M ${axisX(0, W, pad, slots)} ${axisY(vals[0], max, H, pad)}`
  for (let i = 1; i < vals.length; i++) {
    d += ` H ${axisX(i, W, pad, slots)} V ${axisY(vals[i], max, H, pad)}`
  }
  return d
}

// 逐题明细：按技术栈分组排序，同栈内 薄弱 → 掌握 → 未背
export function sortPerQRows(items) {
  return [...(items || [])].sort((a, b) =>
    a.tech_stack.localeCompare(b.tech_stack) || STATUS_ORDER[a.status] - STATUS_ORDER[b.status]
  )
}

// 图谱放大默认选中「掌握数最少」的栈：用于定位短板；并列则取第一个
export function defaultKgStack(bank) {
  const stacks = bank?.stacks || []
  if (!stacks.length) return ''
  return stacks.reduce((a, b) => (b.done < a.done ? b : a)).key
}
