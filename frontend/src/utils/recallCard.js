// 背诵卡片 PNG 生成（Canvas 2D 手绘，无 html2canvas 等第三方依赖）
// 设计：纸白底 + 28px 细格线底纹 + 墨边框，宋体标题 / mono 标注 / 印章红点缀，呼应界面语言
// renderCard(canvas, data) 为纯函数（同步，不碰 DOM/网络），便于测试与复用：
//   data = { date: Date, count: number, questions: [{ title: string, answer: string, retry: boolean }] }
// 卡片高度随题目与答案内容自适应（量 pass 先量排版，再定画布高度）
// exportRecallCard(data)：等页面字体加载完（Noto Serif SC 防豆腐块）→ 渲染 → toBlob → a[download]
const W = 750
const PAPER = '#EDEFEA'
const INK = '#191919'
const INK_45 = 'rgba(25,25,25,.45)'
const INK_25 = 'rgba(25,25,25,.25)'
const GRID = 'rgba(25,25,25,.055)'
const SEAL = '#C0392B'
const SERIF = '"Noto Serif SC", "Songti SC", "SimSun", serif'
const MONO = '"JetBrains Mono", monospace'
const GRID_SIZE = 28        // 与 tokens.css --grid-size 一致
const TITLE_MAX = 28        // 每题题干截断字数
const ANSWER_MAX = 120      // 每题答案摘要截断字数（卡片是清单，不是全文）
const ANSWER_LH = 23        // 答案行高
const LIST_LEFT = 96        // 墨点列 x
const TEXT_LEFT = 118       // 文字列 x
const TEXT_WIDTH = W - TEXT_LEFT - 96  // 答案折行宽度

function pad2(n) { return String(n).padStart(2, '0') }

// 题干预处理短句：去换行/多余空白，超长按 TITLE_MAX 截断
function shortStem(title) {
  const t = String(title || '').replace(/\s+/g, ' ').trim()
  return t.length > TITLE_MAX ? t.slice(0, TITLE_MAX) + '…' : t
}

// 答案摘要：去换行/多余空白，超长按 ANSWER_MAX 截断
function shortAnswer(answer) {
  const t = String(answer || '').replace(/\s+/g, ' ').trim()
  return t.length > ANSWER_MAX ? t.slice(0, ANSWER_MAX) + '…' : t
}

// CJK 友好的逐字折行：按测量宽度断行
function wrapText(ctx, text, maxWidth) {
  const lines = []
  let line = ''
  for (const ch of text) {
    if (line && ctx.measureText(line + ch).width > maxWidth) { lines.push(line); line = ch }
    else line += ch
  }
  if (line) lines.push(line)
  return lines
}

// 纯渲染函数：把背诵卡片画到给定 canvas（宽度固定 750，高度随内容自适应）
export function renderCard(canvas, data) {
  canvas.width = W
  canvas.height = 10   // 先给个小高度拿 ctx 做量 pass，定稿后再设真实高度
  let ctx = canvas.getContext('2d')
  const d = data.date instanceof Date ? data.date : new Date(data.date)
  const questions = data.questions || []
  const count = data.count ?? questions.length

  // ---- 量 pass：逐题排版（题干 + 答案折行），算出内容总高 ----
  const listTop = 372
  const blocks = []
  let y = listTop
  questions.forEach(q => {
    const stem = shortStem(q.title)
    ctx.font = `15px ${SERIF}`
    const answerLines = wrapText(ctx, shortAnswer(q.answer), TEXT_WIDTH)
    blocks.push({ stem, answerLines, retry: !!q.retry, y })
    y += 30 + answerLines.length * ANSWER_LH + 18   // 题干行 30 + 答案行 + 题间距
  })
  const H = Math.max(760, y + 190)   // 底部留给印章与 mono 注记

  // 定稿高度（重设 height 会清空画布与 ctx 状态，之后全部重画）
  canvas.height = H
  ctx = canvas.getContext('2d')

  // ---- 纸白底 + 细格线底纹 ----
  ctx.fillStyle = PAPER
  ctx.fillRect(0, 0, W, H)
  ctx.strokeStyle = GRID
  ctx.lineWidth = 1
  ctx.beginPath()
  for (let x = GRID_SIZE; x < W; x += GRID_SIZE) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, H) }
  for (let gy = GRID_SIZE; gy < H; gy += GRID_SIZE) { ctx.moveTo(0, gy + 0.5); ctx.lineTo(W, gy + 0.5) }
  ctx.stroke()

  // ---- 墨边框（外粗内细双线，图纸感） ----
  ctx.strokeStyle = INK
  ctx.lineWidth = 2.5
  ctx.strokeRect(26, 26, W - 52, H - 52)
  ctx.lineWidth = 1
  ctx.strokeRect(38, 38, W - 76, H - 76)

  const cx = W / 2
  ctx.textAlign = 'center'

  // ---- 顶部：宋体标题 + mono 小字 ----
  ctx.fillStyle = INK
  ctx.font = `700 46px ${SERIF}`
  ctx.fillText('背诵卡片', cx, 124)
  ctx.fillStyle = INK_45
  ctx.font = `13px ${MONO}`
  ctx.fillText('R E C A L L · 记 忆 助 手', cx, 156)

  // 分隔线
  ctx.strokeStyle = INK
  ctx.lineWidth = 1.5
  ctx.beginPath(); ctx.moveTo(90, 188); ctx.lineTo(W - 90, 188); ctx.stroke()

  // ---- 日期 + 题数 ----
  ctx.fillStyle = INK
  ctx.font = `700 38px ${SERIF}`
  ctx.fillText(`${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日`, cx, 262)
  ctx.font = `22px ${SERIF}`
  ctx.fillText(`本轮背诵 ${count} 题`, cx, 312)

  // ---- 题目清单：墨点 + 题干（墨），下随答案摘要（45% 墨，逐字折行）；补答题加印章红小标 ----
  ctx.textAlign = 'left'
  blocks.forEach(b => {
    // 墨点符号
    ctx.fillStyle = INK
    ctx.fillRect(LIST_LEFT, b.y - 9, 7, 7)
    // 题干短句
    ctx.font = `700 19px ${SERIF}`
    ctx.fillText(b.stem, TEXT_LEFT, b.y)
    // 补答标记（印章红）
    if (b.retry) {
      const tw = ctx.measureText(b.stem).width
      ctx.fillStyle = SEAL
      ctx.font = `12px ${MONO}`
      ctx.fillText('补答', TEXT_LEFT + tw + 14, b.y)
    }
    // 答案摘要
    ctx.fillStyle = INK_45
    ctx.font = `15px ${SERIF}`
    b.answerLines.forEach((line, i) => ctx.fillText(line, TEXT_LEFT, b.y + 30 + i * ANSWER_LH))
  })

  // ---- 底部 mono 注记 ----
  ctx.fillStyle = INK_25
  ctx.font = `11px ${MONO}`
  ctx.textAlign = 'left'
  ctx.fillText(`FIG. MEMO — ${d.getFullYear()}.${pad2(d.getMonth() + 1)}.${pad2(d.getDate())}`, 70, H - 66)

  // ---- 右下角「已背诵」印章：印章红细边框 + 轻微旋转，逐字竖排 ----
  ctx.save()
  ctx.translate(W - 150, H - 150)
  ctx.rotate((-7 * Math.PI) / 180)
  ctx.strokeStyle = SEAL
  ctx.lineWidth = 2
  ctx.strokeRect(-46, -78, 92, 156)
  ctx.lineWidth = 1
  ctx.strokeRect(-40, -72, 80, 144)
  ctx.fillStyle = SEAL
  ctx.font = `700 34px ${SERIF}`
  ctx.textAlign = 'center'
  ;['已', '背', '诵'].forEach((ch, i) => ctx.fillText(ch, 0, -34 + i * 48))
  ctx.restore()

  return canvas
}

// 生成并触发下载：背诵卡片-YYYY-MM-DD.png
export async function exportRecallCard(data) {
  await document.fonts.ready   // 等 Noto Serif SC / JetBrains Mono 加载完再画，防中文豆腐块
  const canvas = renderCard(document.createElement('canvas'), data)
  const blob = await new Promise((resolve, reject) =>
    canvas.toBlob(b => (b ? resolve(b) : reject(new Error('canvas.toBlob 返回空'))), 'image/png')
  )
  const d = data.date instanceof Date ? data.date : new Date(data.date)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `背诵卡片-${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}.png`
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
