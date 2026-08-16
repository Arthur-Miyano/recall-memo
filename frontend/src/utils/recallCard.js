// 背诵卡片 PNG 生成（Canvas 2D 手绘，无 html2canvas 等第三方依赖）
// 设计：纸白底 + 28px 细格线底纹 + 墨边框，宋体标题 / mono 标注 / 印章红点缀，呼应界面语言
// renderCard(canvas, data) 为纯函数（同步，不碰 DOM/网络），便于测试与复用：
//   data = { date: Date, count: number, questions: [{ title: string, retry: boolean }] }
// exportRecallCard(data)：等页面字体加载完（Noto Serif SC 防豆腐块）→ 渲染 → toBlob → a[download]
const W = 750
const H = 1000
const PAPER = '#EDEFEA'
const INK = '#191919'
const INK_45 = 'rgba(25,25,25,.45)'
const INK_25 = 'rgba(25,25,25,.25)'
const GRID = 'rgba(25,25,25,.055)'
const SEAL = '#C0392B'
const SERIF = '"Noto Serif SC", "Songti SC", "SimSun", serif'
const MONO = '"JetBrains Mono", monospace'
const GRID_SIZE = 28        // 与 tokens.css --grid-size 一致
const MAX_ROWS = 14         // 题目清单最多行数，超出折叠为「…… 等 N 题」
const TITLE_MAX = 20        // 每题题干截断字数

function pad2(n) { return String(n).padStart(2, '0') }

// 题干预处理短句：去换行/多余空白，≤20 字截断
function shortStem(title) {
  const t = String(title || '').replace(/\s+/g, ' ').trim()
  return t.length > TITLE_MAX ? t.slice(0, TITLE_MAX) + '…' : t
}

// 纯渲染函数：把背诵卡片画到给定 canvas（尺寸固定 750×1000）
export function renderCard(canvas, data) {
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')
  const d = data.date instanceof Date ? data.date : new Date(data.date)
  const questions = data.questions || []
  const count = data.count ?? questions.length

  // ---- 纸白底 + 细格线底纹 ----
  ctx.fillStyle = PAPER
  ctx.fillRect(0, 0, W, H)
  ctx.strokeStyle = GRID
  ctx.lineWidth = 1
  ctx.beginPath()
  for (let x = GRID_SIZE; x < W; x += GRID_SIZE) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, H) }
  for (let y = GRID_SIZE; y < H; y += GRID_SIZE) { ctx.moveTo(0, y + 0.5); ctx.lineTo(W, y + 0.5) }
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

  // ---- 题目清单：墨点引导，每题一行；补答题加印章红小标 ----
  const listTop = 372
  const rowH = 44
  const rows = questions.slice(0, MAX_ROWS)
  const rest = questions.length - rows.length
  ctx.textAlign = 'left'
  rows.forEach((q, i) => {
    const y = listTop + i * rowH
    // 墨点符号
    ctx.fillStyle = INK
    ctx.fillRect(96, y - 9, 7, 7)
    // 题干短句
    ctx.font = `19px ${SERIF}`
    ctx.fillText(shortStem(q.title), 118, y)
    // 补答标记（印章红）
    if (q.retry) {
      const tw = ctx.measureText(shortStem(q.title)).width
      ctx.fillStyle = SEAL
      ctx.font = `12px ${MONO}`
      ctx.fillText('补答', 118 + tw + 14, y)
    }
  })
  if (rest > 0) {
    ctx.fillStyle = INK_45
    ctx.font = `16px ${SERIF}`
    ctx.fillText(`…… 等 ${questions.length} 题`, 118, listTop + rows.length * rowH)
  }

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
