// 首页抽屉的选择记忆：上一次选的技术栈/题量存 localStorage，下次进首页默认带上。
// 存取与纯函数分离，方便 node --test 直接测解析逻辑（node 环境没有 localStorage）。
const KEY = 'recall.home-prefs'

export function loadHomePrefs() {
  try {
    if (typeof localStorage === 'undefined') return {}
    return JSON.parse(localStorage.getItem(KEY)) || {}
  } catch {
    return {} // 数据损坏或隐私模式：当作没存过
  }
}

// mode: 'memorize' / 'interview'；pref: { stack, count }
export function saveHomePref(mode, pref) {
  if (typeof localStorage === 'undefined') return
  try {
    const all = loadHomePrefs()
    all[mode] = pref
    localStorage.setItem(KEY, JSON.stringify(all))
  } catch { /* 写失败（如隐私模式）就放弃，不影响使用 */ }
}

// 技术栈选项是 [{value, label}] 或字符串数组，取出用于比较的 value
function optionValue(o) {
  return (o && typeof o === 'object') ? o.value : o
}

// 找回上次选的技术栈下标集合（多选）；savedValues 为新数组或旧单值字符串；都找不到回退默认下标
export function resolveStackIndices(options, savedValues, fallback) {
  const vals = Array.isArray(savedValues) ? savedValues : (savedValues ? [savedValues] : [])
  const set = new Set()
  for (const v of vals) {
    const i = options.findIndex(o => optionValue(o) === v)
    if (i >= 0) set.add(i)
  }
  if (set.size === 0) set.add(fallback)
  return set
}

// 找回上次选的技术栈下标；找不到（比如栈被删了）回退默认下标
export function resolveStackIndex(options, savedValue, fallback) {
  const i = options.findIndex(o => optionValue(o) === savedValue)
  return i >= 0 ? i : fallback
}

// 恢复题量：命中胶囊返回 { index }；不在胶囊里但在 1~max 内返回 { custom: n }（自由输入）；
// 都没有（没存过/越界）返回 { index: fallback }
export function resolveCount(savedCount, capsules, fallback, max = 20) {
  const n = Number(savedCount)
  if (Number.isInteger(n) && n >= 1) {
    const i = capsules.indexOf(n)
    if (i >= 0) return { index: i }
    if (n <= max) return { custom: n }
  }
  return { index: fallback }
}
