// 把文本拆成片段：英文单词（可点查词）与普通文本
// 反引号包裹的代码段不拆词——代码标识符（beforeRouteEnter、__init__）不是查词对象
const CODE_RE = /(`[^`]*`)/
const WORD_RE = /[A-Za-z]{2,}(?:[-'][A-Za-z]+)*/g

export function splitWordSegments(text) {
  const segs = []
  for (const part of String(text ?? '').split(CODE_RE)) {
    if (!part) continue
    if (part.startsWith('`')) {
      segs.push({ kind: 'text', text: part })
      continue
    }
    let last = 0
    WORD_RE.lastIndex = 0
    let m
    while ((m = WORD_RE.exec(part))) {
      if (m.index > last) segs.push({ kind: 'text', text: part.slice(last, m.index) })
      segs.push({ kind: 'word', text: m[0] })
      last = m.index + m[0].length
    }
    if (last < part.length) segs.push({ kind: 'text', text: part.slice(last) })
  }
  return segs
}
