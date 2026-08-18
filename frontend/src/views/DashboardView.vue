<script setup>
// 屏幕四：仪表盘（背诵档案台）
// 职责：日历热力 / 7 天趋势阶梯折线 / 各栈正确率像素柱 / 知识图谱 / 今日建议 / 录入题库 / 模型密钥设置
// 数据流（真实接口，任一失败回退 mock/dashboard.js 并 console.warn）：
//   GET /api/stats/overview     —— 各栈正确率、覆盖度
//   GET /api/stats/daily?days=N —— 月历热力（90 天，前端按月切换）与 7 天趋势、连续打卡
//   GET /api/bank/overview      —— 知识图谱小卡片概览计数 + 今日建议
//   GET /api/stats/llm-usage?days=30 —— API 消耗（花费/请求/Tokens 总计 + 每日柱状 + 按模型）
// 放大视图（点击卡片打开纸张 modal，数据流见 api/bank.js）：
//   每日记录 → /api/stats/daily-detail?days=90（逐日明细）+ /api/stats/daily?days=90（月历热力，前端按月切换）
//   趋势     → /api/stats/daily?days=30（成功/失败双色阶梯折线）
//   正确率   → /api/stats/per-question（逐题明细表）
//   图谱     → /api/bank/overview + /api/stats/per-question（大画布，节点点击看题干/答案/得分记录）
//   建议     → /api/stats/per-question + /api/sessions/retry-queue + POST /api/assistant/chat {quick:plan}
// 录入题库：ImportPanel → POST /api/bank/import，入库成功后重拉卡片数据
// 图表说明：折线与知识图谱为手绘 SVG（图纸感直角转折、像素方块节点），
//   有意不用 ECharts —— 像素美学是设计的一部分
import { ref, computed, onMounted } from 'vue'
import SettingsPanel from '../components/SettingsPanel.vue'
import DashboardModal from '../components/DashboardModal.vue'
import ImportPanel from '../components/ImportPanel.vue'
import InkCalendar from '../components/InkCalendar.vue'
import { dashboard as mockDb } from '../mock/dashboard'
import { getStatsOverview, getStatsDaily, getBankOverview, getLlmUsage } from '../api'
import {
  getStatsDailyDetail, getStatsPerQuestion, getRetryQueue, postAssistantPlan,
} from '../api/bank'
import '../styles/dashboard.css'

// 整体数据：先渲染 mock 骨架，真实数据到位后逐块替换
// 日历字段统一为 InkCalendar 的 items 结构 [{date, total_count}]；
// mock 兜底时把 28 个等级数字映射为最近 28 天的日期，保证结构一致
const db = ref({ ...mockDb, calendar: mockCalItems() })

// 本地日期 → 'YYYY-MM-DD'（与后端 daily 接口口径一致）
function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function mockCalItems() {
  return mockDb.calendar.map((v, i) => {
    const d = new Date()
    d.setDate(d.getDate() - (27 - i))
    return { date: fmtDate(d), total_count: v }
  })
}

// 小卡片方格条：最近 28 天（2 行 × 14 列），格内显示日号，今天印章红框
const strip28 = computed(() => {
  const countMap = Object.fromEntries((db.value.calendar || []).map(c => [c.date, c.total_count]))
  const days = []
  for (let i = 27; i >= 0; i--) {
    const d = new Date()
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
})

const WEEKDAYS_CN = ['日', '一', '二', '三', '四', '五', '六']
// cell.status → 图谱节点状态
const CELL2NODE = { done: 'mastered', weak: 'weak', todo: 'todo' }
// 同知识点多题时的序号角标（①~⑳，超出兜底 ·n）
const CIRCLED = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩','⑪','⑫','⑬','⑭','⑮','⑯','⑰','⑱','⑲','⑳']
// 图谱节点主标签：知识点（分组名），>8 字截断加 …；同知识点多题加圈号序号
function kgLabel(groupName, idx, count) {
  const base = groupName.length > 8 ? groupName.slice(0, 8) + '…' : groupName
  if (count <= 1) return base
  return `${base} ${idx <= 20 ? CIRCLED[idx - 1] : '·' + idx}`
}

// 卡片数据加载（首屏 + 录入成功后刷新共用）
async function loadDashboard() {
  try {
    const [ov, daily90, daily7, bank, usage] = await Promise.all([
      getStatsOverview(), getStatsDaily(90), getStatsDaily(7), getBankOverview(), getLlmUsage(30),
    ])
    // 连续打卡：从今天往前数有答题的天数
    let streak = 0
    for (let i = daily7.items.length - 1; i >= 0; i--) {
      if (daily7.items[i].total_count > 0) streak++
      else break
    }
    db.value = {
      headMeta: [
        `已覆盖 ${ov.covered} / ${ov.total_questions} 题 · 连续打卡 ${streak} 天`,
        `数据截至 ${new Date().toLocaleDateString('zh-CN')}`,
      ],
      // 月历热力：一次拉 90 天，InkCalendar 前端按月切换；等级逻辑在组件内（0~4 级）
      calendar: daily90.items,
      trend: {
        values: daily7.items.map(d => d.total_count),
        days: daily7.items.map(d => WEEKDAYS_CN[new Date(d.date + 'T00:00:00').getDay()]),
        max: Math.max(...daily7.items.map(d => d.total_count), 1),
      },
      accuracy: Object.entries(ov.per_stack).map(([name, s]) => ({
        name: name.toUpperCase(),
        pct: s.pass_rate == null ? 0 : Math.round(s.pass_rate * 100),
      })),
      stackOv: buildStackOverview(bank),
      suggestions: buildSuggestions(bank),
      usage,                              // API 消耗：totals + 30 天 daily + models
      settings: mockDb.settings, // 设置面板自行请求真实接口，这里仅占位
    }
  } catch (e) {
    console.warn('[dashboard] 统计数据获取失败，回退 mock 数据：', e.message)
  }
}
onMounted(loadDashboard)

// 知识图谱小卡片（概览态）：不画节点图，每栈只统计 掌握/薄弱/未背 计数 + 完成比例
function buildStackOverview(bank) {
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
function buildSuggestions(bank) {
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

// ---- 7 天趋势折线（SVG 手绘，坐标换算与原型一致） ----
const W = 560, H = 160, pad = 28
const px = i => pad + i * (W - pad * 2) / 6
const py = v => H - pad - v * (H - pad * 2) / db.value.trend.max
// 阶梯折线：先水平后垂直的直角转折
const trendPath = computed(() => {
  const vals = db.value.trend.values
  let d = `M ${px(0)} ${py(vals[0])}`
  for (let i = 1; i < vals.length; i++) d += ` H ${px(i)} V ${py(vals[i])}`
  return d
})
const gridLines = computed(() => Array.from({ length: db.value.trend.max + 1 }, (_, g) => g))

// 正确率像素柱：pct → 10 格
function accCells(p) { return Math.round(p / 10) }

// ---- API 消耗（LLM 用量）：柱状图 ----
// 通用柱条换算：items → 等宽柱（key 为数值字段），柱高 ∝ 数值
function makeBars(items, key, W, H, pad, bw) {
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
const fmtInt = n => Number(n || 0).toLocaleString('en-US')
const fmtBig = v => (v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(1) + 'k' : String(Math.round(v * 100) / 100))
const UW = 560, UH = 120, upad = 28
// 小卡片：近 30 天花费柱状
const usageBars = computed(() => makeBars(db.value.usage?.daily || [], 'cost', UW, UH, upad, 10))

/* ==================== 放大视图 ==================== */
// modalKey：'' | calendar | trend | accuracy | graph | suggest
const modalKey = ref('')
const modalData = ref(null)   // 当前放大视图的数据载荷（按 key 结构不同）
const modalLoading = ref(false)
const showImport = ref(false)

const MODAL_META = {
  calendar: { title: '每日背诵记录 · 月历（近 90 天）', fig: 'FIG.04-A+' },
  trend: { title: '答题趋势 · 近 30 天', fig: 'FIG.04-B+' },
  accuracy: { title: '逐题明细 · 各技术栈正确率', fig: 'FIG.04-C+' },
  graph: { title: '知识图谱 · 全题状态', fig: 'FIG.04-D+' },
  suggest: { title: '今日建议背诵 · 完整清单', fig: 'FIG.04-E+' },
  usage: { title: 'API 消耗 · LLM 用量（近 30 天）', fig: 'FIG.04-F+' },
}
const modalMeta = computed(() => MODAL_META[modalKey.value] || { title: '', fig: '' })

// 打开放大视图：按卡片类型拉取对应数据，失败 console.warn + 空态（不白屏）
async function openModal(key) {
  modalKey.value = key
  modalData.value = null
  modalLoading.value = true
  kgSelected.value = null
  planReply.value = ''
  try {
    if (key === 'calendar') {
      // 一次拉 90 天：月历前端按月切换，点击日期展开当天明细
      const [detail, daily] = await Promise.all([getStatsDailyDetail(90), getStatsDaily(90)])
      modalData.value = { detail, daily }
    } else if (key === 'trend') {
      modalData.value = { daily: await getStatsDaily(30) }
    } else if (key === 'accuracy') {
      modalData.value = { perQ: await getStatsPerQuestion() }
    } else if (key === 'graph') {
      const [bank, perQ] = await Promise.all([getBankOverview(), getStatsPerQuestion()])
      modalData.value = { bank, perQMap: Object.fromEntries(perQ.items.map(q => [q.question_id, q])) }
      kgStackKey.value = defaultKgStack(bank) // 打开时默认落在掌握最少的栈
    } else if (key === 'suggest') {
      const [perQ, retry] = await Promise.all([getStatsPerQuestion(), getRetryQueue()])
      modalData.value = { perQ, retry }
    } else if (key === 'usage') {
      usageMetric.value = 'cost'
      modalData.value = { usage: await getLlmUsage(30) }
    }
  } catch (e) {
    console.warn(`[dashboard] 放大视图数据获取失败（${key}）：`, e.message)
  } finally {
    modalLoading.value = false
  }
}
function closeModal() { modalKey.value = ''; modalData.value = null }

// ---- 放大 · 每日背诵记录：date → records 映射，供 InkCalendar 点击日期展开当天明细 ----
const calDetailMap = computed(() =>
  Object.fromEntries((modalData.value?.detail.items || []).map(d => [d.date, d.records]))
)

// ---- 放大 · 30 天趋势：成功（墨实线）/ 失败（红虚线）双色阶梯折线 ----
const TW = 920, TH = 220, tpad = 30
const tpx = i => tpad + i * (TW - tpad * 2) / 29
const trend30Max = computed(() => {
  const items = modalData.value?.daily.items || []
  return Math.max(...items.map(d => Math.max(d.success_count, d.fail_count)), 1)
})
const tpy = v => TH - tpad - v * (TH - tpad * 2) / trend30Max.value
function stepPath(vals) {
  if (!vals.length) return ''
  let d = `M ${tpx(0)} ${tpy(vals[0])}`
  for (let i = 1; i < vals.length; i++) d += ` H ${tpx(i)} V ${tpy(vals[i])}`
  return d
}
const okPath = computed(() => stepPath((modalData.value?.daily.items || []).map(d => d.success_count)))
const failPath = computed(() => stepPath((modalData.value?.daily.items || []).map(d => d.fail_count)))
const trend30Grid = computed(() => Array.from({ length: trend30Max.value + 1 }, (_, g) => g))

// ---- 放大 · API 消耗：花费/请求/Tokens 三指标切换柱状图 + 按模型明细 ----
const USAGE_METRICS = [
  { key: 'cost', label: '消费金额 ¥' },
  { key: 'requests', label: 'API 请求' },
  { key: 'tokens', label: 'Tokens' },
]
const usageMetric = ref('cost')
const UW2 = 920, UH2 = 240, upad2 = 30
const usageBig = computed(() =>
  makeBars(modalData.value?.usage.daily || [], usageMetric.value, UW2, UH2, upad2, 18)
)
// Y 轴刻度标签：cost 带 ¥ 与两位小数，其余按量缩写
function usageAxisFmt(v) {
  return usageMetric.value === 'cost' ? `¥${v.toFixed(2)}` : fmtBig(v)
}

// ---- 放大 · 正确率：逐题明细按技术栈分组排序，未背的排最后 ----
const STATUS_ORDER = { weak: 0, done: 1, todo: 2 }
const perQRows = computed(() => {
  const items = [...(modalData.value?.perQ.items || [])]
  return items.sort((a, b) =>
    a.tech_stack.localeCompare(b.tech_stack) || STATUS_ORDER[a.status] - STATUS_ORDER[b.status]
  )
})
const STATUS_CN = { done: '掌握', weak: '薄弱', todo: '未背' }

// ---- 放大 · 知识图谱：一次一个技术栈（Tab 切换）+ 纸墨 3D ----
// 大画布只画当前栈：根节点居中 + 题目节点网格排布；节点主标签为知识点（分组名），
// 完整题干在悬停 title 与点击详情里（174 题后题干截断已无法区分题目）
const kgSelected = ref(null)   // 选中的 per-question 条目
const kgStackKey = ref('')     // 当前选中的技术栈 key
// 技术栈 Tab 数据：名称 + 掌握/总数
const kgTabs = computed(() =>
  (modalData.value?.bank.stacks || []).map(s => ({
    key: s.key, label: s.name.toUpperCase(), done: s.done, total: s.total,
  }))
)
// 默认选中「掌握数最少」的栈：图谱放大用于定位短板，先落在最弱的栈上；并列则取第一个
function defaultKgStack(bank) {
  const stacks = bank?.stacks || []
  if (!stacks.length) return ''
  return stacks.reduce((a, b) => (b.done < a.done ? b : a)).key
}
function switchKgStack(key) {
  if (kgStackKey.value === key) return
  kgStackKey.value = key
  kgSelected.value = null      // 切栈后清掉上一栈的节点详情
  kgTilt.value = { rx: 0, ry: 0 }
}
const KG_COLS = 3              // 单栈画布题目节点列数
const kgBig = computed(() => {
  const perQMap = modalData.value?.perQMap || {}
  const stack = (modalData.value?.bank.stacks || []).find(s => s.key === kgStackKey.value)
  if (!stack) return { root: null, kids: [], edges: [], boxH: 300 }
  const CX = 460, ROOT_Y = 52  // 根节点：画布顶部居中
  const kids = []
  const edges = []
  let i = 0
  stack.groups.forEach(g => g.cells.forEach((c, ci) => {
    const perQ = perQMap[c.question_id]
    const kid = {
      qid: c.question_id,
      x: 170 + (i % KG_COLS) * 290,
      y: 140 + Math.floor(i / KG_COLS) * 48,
      title: kgLabel(g.name, ci + 1, g.cells.length),
      stem: perQ ? perQ.stem : (c.label || g.name),
      score: perQ && perQ.latest_score != null ? `${Math.round(perQ.latest_score)}分` : '未背',
      s: CELL2NODE[c.status] || 'todo',
    }
    kids.push(kid)
    edges.push({ x1: CX, y1: ROOT_Y, x2: kid.x, y2: kid.y })
    i++
  }))
  const boxH = Math.max(300, 140 + Math.ceil(i / KG_COLS) * 48 + 24)
  return { root: { x: CX, y: ROOT_Y, label: stack.name.toUpperCase() }, kids, edges, boxH }
})
function pickNode(kid) {
  kgSelected.value = modalData.value?.perQMap?.[kid.qid] || null
}

// ---- 纸墨 3D：画布平面基础倾斜 rotateX(10deg)，光标移动时叠加 ±4deg 视差 ----
// 纯 CSS transform（perspective + drop-shadow 偏移投影），不引入 3D 库；prefers-reduced-motion 时禁用
const kgStageEl = ref(null)
const kgTilt = ref({ rx: 0, ry: 0 })  // 视差偏移（叠加在基础倾斜上）
const kgReduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
const KG_BASE_TILT = 10               // 基础倾斜角度（8~12deg 区间的克制取值）
function kgParallax(e) {
  if (kgReduceMotion) return
  const el = kgStageEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  const nx = (e.clientX - r.left) / r.width - 0.5   // -0.5 ~ 0.5
  const ny = (e.clientY - r.top) / r.height - 0.5
  kgTilt.value = { rx: -ny * 8, ry: nx * 8 }        // 各方向 ±4deg 内
}
function kgParallaxEnd() { kgTilt.value = { rx: 0, ry: 0 } }
const kgPlaneStyle = computed(() => {
  if (kgReduceMotion) return {}
  const rx = (KG_BASE_TILT + kgTilt.value.rx).toFixed(2)
  const ry = kgTilt.value.ry.toFixed(2)
  return { transform: `rotateX(${rx}deg) rotateY(${ry}deg)` }
})

// ---- 放大 · 今日建议：全部薄弱题（按分升序）+ 待补答队列，各附一句理由 ----
const suggestWeak = computed(() => {
  const retryIds = new Set((modalData.value?.retry.items || []).map(r => r.question_id))
  return (modalData.value?.perQ.items || [])
    .filter(q => q.status === 'weak')
    .sort((a, b) => (a.latest_score ?? 0) - (b.latest_score ?? 0))
    .map(q => ({
      ...q,
      reason: `最新得分 ${Math.round(q.latest_score)} 分，低于及格线 60`
        + (retryIds.has(q.question_id) ? '，在待补答队列中' : '，建议优先重背'),
    }))
})
const suggestRetry = computed(() => modalData.value?.retry.items || [])

// 「问问助手怎么安排」：POST /api/assistant/chat {quick:plan}，加载中有状态
const planLoading = ref(false)
const planReply = ref('')
async function askPlan() {
  if (planLoading.value) return
  planLoading.value = true
  planReply.value = ''
  try {
    const resp = await postAssistantPlan()
    planReply.value = resp.reply
  } catch (e) {
    console.warn('[dashboard] 助手计划获取失败：', e.message)
    planReply.value = `助手暂时 unavailable：${e.message}`
  } finally {
    planLoading.value = false
  }
}

// 录入完成（有题入库）：重拉卡片数据，让覆盖数/图谱/建议立即更新
function onImported() { loadDashboard() }
</script>

<template>
  <section class="screen active">
    <div class="rv-head">
      <div>
        <div class="mono" style="font-size:11px;letter-spacing:.14em;color:var(--ink-45);margin-bottom:10px">DASHBOARD — 智能助理 AGENT</div>
        <h1 class="rv-title">背诵档案台</h1>
      </div>
      <span class="spacer"></span>
      <div class="meta">{{ db.headMeta[0] }}<br>{{ db.headMeta[1] }}</div>
    </div>

    <div class="db-grid">
      <div style="display:flex;flex-direction:column;gap:28px">
        <!-- 日历热力格：近 28 天方格条（格内日号，点击开放大月历） -->
        <div class="db-panel db-click" @click="openModal('calendar')">
          <h2>每日背诵记录 <span class="n">FIG.04-A</span></h2>
          <div class="cal-strip-range">近 28 天 · {{ strip28[0].label }} — {{ strip28[27].label }}</div>
          <div class="cal-strip">
            <span
              v-for="c in strip28" :key="c.date"
              class="cell" :class="[`l${c.level}`, { today: c.isToday }]"
              :title="c.tip"
            >{{ c.dayNum }}</span>
          </div>
          <div class="cal-legend">少 <i style="background:var(--ink-12)"></i><i style="background:rgba(25,25,25,.55)"></i><i style="background:var(--ink)"></i> 多</div>
          <span class="zoom-hint">点击放大 ▸</span>
        </div>
        <!-- 近 7 天答题趋势：阶梯折线 -->
        <div class="db-panel db-click" @click="openModal('trend')">
          <h2>近 7 天答题趋势 <span class="n">FIG.04-B</span></h2>
          <svg class="chart-line" viewBox="0 0 560 160">
            <!-- 坐标格横线 + Y 轴刻度 -->
            <template v-for="g in gridLines" :key="'g' + g">
              <line
                :x1="pad" :y1="py(g)" :x2="W - pad" :y2="py(g)"
                stroke="rgba(25,25,25,.12)" stroke-width="1"
                :stroke-dasharray="g ? '2 4' : undefined"
              />
              <text :x="pad - 8" :y="py(g) + 4" text-anchor="end" font-family="var(--mono)" font-size="9" fill="rgba(25,25,25,.45)">{{ g }}</text>
            </template>
            <!-- X 轴星期标签 -->
            <text
              v-for="(d, i) in db.trend.days" :key="'d' + i"
              :x="px(i)" :y="H - 8" text-anchor="middle"
              font-family="var(--mono)" font-size="9" fill="rgba(25,25,25,.45)"
            >周{{ d }}</text>
            <!-- 阶梯折线 + 像素方块数据点 + 数值 -->
            <path :d="trendPath" fill="none" stroke="var(--ink)" stroke-width="2" />
            <template v-for="(v, i) in db.trend.values" :key="'p' + i">
              <rect :x="px(i) - 4" :y="py(v) - 4" width="8" height="8" fill="var(--paper-hi)" stroke="var(--ink)" stroke-width="1.5" />
              <text :x="px(i)" :y="py(v) - 12" text-anchor="middle" font-family="var(--mono)" font-size="10" fill="var(--ink)">{{ v }}</text>
            </template>
          </svg>
          <span class="zoom-hint">点击放大 ▸</span>
        </div>
        <!-- 各技术栈正确率：像素柱 -->
        <div class="db-panel db-click" @click="openModal('accuracy')">
          <h2>各技术栈正确率 <span class="n">FIG.04-C</span></h2>
          <div class="acc-row" v-for="a in db.accuracy" :key="a.name">
            <span class="name">{{ a.name }}</span>
            <div class="pixbar">
              <i v-for="n in 10" :key="n" :class="{ off: n > accCells(a.pct) }"></i>
            </div>
            <span class="pct">{{ a.pct }}%</span>
          </div>
          <span class="zoom-hint">点击放大 ▸</span>
        </div>
        <!-- 模型与密钥配置 -->
        <SettingsPanel />
      </div>

      <div style="display:flex;flex-direction:column;gap:28px">
        <!-- 知识图谱（概览态：每栈计数 + 进度，点击开放大视图看全图） -->
        <div class="db-panel db-click" @click="openModal('graph')">
          <h2>知识图谱 <span class="n">FIG.04-D</span></h2>
          <div class="kg-ov">
            <div class="kg-ov-row" v-for="s in db.stackOv" :key="s.key">
              <div class="kg-ov-line">
                <span class="nm">{{ s.label }}</span>
                <span class="chips">
                  <span class="chip m"><i></i>{{ s.done }}</span>
                  <span class="chip w"><i></i>{{ s.weak }}</span>
                  <span class="chip t"><i></i>{{ s.todo }}</span>
                </span>
                <span class="frac">{{ s.done }}/{{ s.total }}</span>
              </div>
              <div class="kg-ov-bar"><i :style="{ width: (s.total ? (s.done / s.total * 100) : 0) + '%' }"></i></div>
            </div>
          </div>
          <div class="kg-legend">
            <span><i style="background:var(--ink)"></i>掌握</span>
            <span><i style="border:1.5px dashed var(--seal)"></i>薄弱</span>
            <span><i style="background:var(--ink-12)"></i>未覆盖</span>
          </div>
          <span class="zoom-hint">点击放大 ▸</span>
        </div>
        <!-- 今日建议背诵 -->
        <div class="db-panel db-click" @click="openModal('suggest')">
          <h2>今日建议背诵 <span class="n">FIG.04-E</span></h2>
          <ul class="suggest">
            <li v-for="(sg, i) in db.suggestions" :key="i">
              <span class="d">{{ sg.d }}</span><span class="t">{{ sg.t }}</span><span class="s">{{ sg.s }}</span>
            </li>
            <li v-if="!db.suggestions.length"><span class="d">OK</span><span class="t">暂无薄弱题，保持节奏</span><span class="s">—</span></li>
          </ul>
          <span class="zoom-hint">点击放大 ▸</span>
        </div>
        <!-- API 消耗（LLM 用量）：总计三项 + 近 30 天花费柱状，点击放大看请求/Tokens 与按模型明细 -->
        <div class="db-panel db-click" @click="openModal('usage')">
          <h2>API 消耗 <span class="n">FIG.04-F</span></h2>
          <div class="usage-totals">
            <div class="ut"><div class="k">消费金额</div><div class="v">¥{{ db.usage.totals.cost.toFixed(2) }}</div></div>
            <div class="ut"><div class="k">API 请求</div><div class="v">{{ fmtInt(db.usage.totals.requests) }}</div></div>
            <div class="ut"><div class="k">Tokens</div><div class="v">{{ fmtInt(db.usage.totals.tokens) }}</div></div>
          </div>
          <svg class="chart-line" viewBox="0 0 560 120">
            <!-- 基线 + 顶格虚线 + Y 轴刻度 -->
            <line :x1="upad" :y1="UH - upad" :x2="UW - upad" :y2="UH - upad" stroke="rgba(25,25,25,.12)" stroke-width="1" />
            <line :x1="upad" :y1="upad" :x2="UW - upad" :y2="upad" stroke="rgba(25,25,25,.12)" stroke-width="1" stroke-dasharray="2 4" />
            <text :x="upad - 8" :y="upad + 4" text-anchor="end" font-family="var(--mono)" font-size="9" fill="rgba(25,25,25,.45)">¥{{ usageBars.max.toFixed(2) }}</text>
            <text :x="upad - 8" :y="UH - upad + 4" text-anchor="end" font-family="var(--mono)" font-size="9" fill="rgba(25,25,25,.45)">0</text>
            <!-- 花费柱条（墨色，悬停看日期与金额） -->
            <template v-for="b in usageBars.bars" :key="b.i">
              <rect v-if="b.h > 0" :x="b.x" :y="b.y" width="10" :height="b.h" fill="var(--ink)">
                <title>{{ b.date }} · ¥{{ b.v.toFixed(4) }}</title>
              </rect>
            </template>
            <!-- X 轴：每 10 天一个 MM-DD 标签 -->
            <text
              v-for="b in usageBars.bars" :key="'x' + b.i"
              v-show="b.i % 10 === 0 || b.i === usageBars.bars.length - 1"
              :x="b.x + 5" :y="UH - 8" text-anchor="middle"
              font-family="var(--mono)" font-size="9" fill="rgba(25,25,25,.45)"
            >{{ b.date.slice(5) }}</text>
          </svg>
          <span class="zoom-hint">点击放大 ▸</span>
        </div>
        <!-- 录入题库入口 -->
        <div class="db-panel db-click" @click="showImport = true">
          <h2>录入题库 <span class="n">IMPORT</span></h2>
          <ul class="suggest">
            <li><span class="d">NEW</span><span class="t">粘贴题目文本或选择文件，自动清洗去重、AI 补全答案与分类</span><span class="s">▸</span></li>
          </ul>
          <span class="zoom-hint">点击打开 ▸</span>
        </div>
      </div>
    </div>

    <!-- 放大视图 modal -->
    <DashboardModal v-if="modalKey" :title="modalMeta.title" :fig="modalMeta.fig" @close="closeModal">
      <div v-if="modalLoading" class="dm-loading">数据铺陈中 …</div>
      <div v-else-if="!modalData" class="dm-empty">数据暂未备好（接口异常详见控制台）</div>

      <template v-else>
        <!-- 放大 · 每日背诵记录：完整月历（翻月 + 点击日期展开当天明细） -->
        <template v-if="modalKey === 'calendar'">
          <InkCalendar :items="modalData.daily.items" :details="calDetailMap" style="max-width:600px;margin:0 auto" />
          <div class="cal-legend" style="margin-top:12px">少 <i style="background:var(--ink-12)"></i><i style="background:rgba(25,25,25,.55)"></i><i style="background:var(--ink)"></i> 多（点击有记录的日期展开当天明细）</div>
          <div v-if="!modalData.detail.items.length" class="dm-empty" style="margin-top:14px">近 90 天暂无答题记录</div>
        </template>

        <!-- 放大 · 30 天趋势：成功/失败双色阶梯折线 -->
        <template v-else-if="modalKey === 'trend'">
          <svg class="chart-line" :viewBox="`0 0 ${TW} ${TH}`" style="width:100%;height:auto">
            <template v-for="g in trend30Grid" :key="'g' + g">
              <line
                :x1="tpad" :y1="tpy(g)" :x2="TW - tpad" :y2="tpy(g)"
                stroke="rgba(25,25,25,.12)" stroke-width="1"
                :stroke-dasharray="g ? '2 4' : undefined"
              />
              <text :x="tpad - 8" :y="tpy(g) + 4" text-anchor="end" font-family="var(--mono)" font-size="9" fill="rgba(25,25,25,.45)">{{ g }}</text>
            </template>
            <!-- X 轴：每 5 天一个 MM-DD 标签 -->
            <text
              v-for="(d, i) in modalData.daily.items" :key="'d' + i"
              v-show="i % 5 === 0 || i === modalData.daily.items.length - 1"
              :x="tpx(i)" :y="TH - 8" text-anchor="middle"
              font-family="var(--mono)" font-size="9" fill="rgba(25,25,25,.45)"
            >{{ d.date.slice(5) }}</text>
            <!-- 失败：印章红虚线阶梯 -->
            <path :d="failPath" fill="none" stroke="var(--seal)" stroke-width="1.5" stroke-dasharray="4 3" />
            <!-- 成功：墨色实线阶梯 + 像素方块数据点 -->
            <path :d="okPath" fill="none" stroke="var(--ink)" stroke-width="2" />
            <template v-for="(d, i) in modalData.daily.items" :key="'p' + i">
              <rect v-if="d.success_count" :x="tpx(i) - 3.5" :y="tpy(d.success_count) - 3.5" width="7" height="7" fill="var(--paper-hi)" stroke="var(--ink)" stroke-width="1.2" />
              <rect v-if="d.fail_count" :x="tpx(i) - 3" :y="tpy(d.fail_count) - 3" width="6" height="6" fill="var(--paper-hi)" stroke="var(--seal)" stroke-width="1" />
            </template>
          </svg>
          <div class="dm-trend-legend">
            <span><i></i>成功（得分 ≥60）</span>
            <span><i class="fail"></i>失败 / 跳过</span>
          </div>
        </template>

        <!-- 放大 · 逐题明细表 -->
        <template v-else-if="modalKey === 'accuracy'">
          <table class="dm-table">
            <thead>
              <tr><th>题目</th><th>技术栈</th><th>知识点</th><th>最近得分</th><th>次数</th><th>状态</th></tr>
            </thead>
            <tbody>
              <tr v-for="q in perQRows" :key="q.question_id">
                <td>{{ q.stem.length > 26 ? q.stem.slice(0, 25) + '…' : q.stem }}</td>
                <td class="mono dim">{{ q.tech_stack.toUpperCase() }}</td>
                <td class="dim">{{ q.group }}</td>
                <td class="mono">{{ q.latest_score == null ? '—' : Math.round(q.latest_score) }}</td>
                <td class="mono">{{ q.attempts }}</td>
                <td><span class="dm-stamp" :class="q.status">{{ STATUS_CN[q.status] }}</span></td>
              </tr>
            </tbody>
          </table>
        </template>

        <!-- 放大 · 知识图谱：技术栈 Tab（一次一栈）+ 纸墨 3D 画布 + 节点详情 -->
        <template v-else-if="modalKey === 'graph'">
          <!-- 技术栈 Tab：胶囊风格，带 掌握/总数 -->
          <div class="kg-tabs">
            <button
              v-for="t in kgTabs" :key="t.key"
              class="kg-tab" :class="{ active: t.key === kgStackKey }"
              @click="switchKgStack(t.key)"
            >
              {{ t.label }}<span class="kg-tab-num">{{ t.done }}/{{ t.total }}</span>
            </button>
          </div>
          <!-- 3D 舞台：perspective 在舞台，平面基础倾斜 + 光标视差（reduced-motion 禁用） -->
          <div ref="kgStageEl" class="dm-kg-stage" @mousemove="kgParallax" @mouseleave="kgParallaxEnd">
            <div class="dm-kg-plane" :style="kgPlaneStyle">
              <svg :key="kgStackKey" class="dm-kg dm-kg-in" :viewBox="`0 0 920 ${kgBig.boxH}`" style="width:100%;height:auto">
                <line
                  v-for="(e, i) in kgBig.edges" :key="'e' + i"
                  class="lk" :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
                />
                <template v-for="k in kgBig.kids" :key="'n' + k.qid">
                  <g class="nd" @click.stop="pickNode(k)">
                    <title>{{ k.stem }}</title>
                    <rect
                      class="node-box" :class="['node-' + k.s, { 'node-sel': kgSelected && kgSelected.question_id === k.qid }]"
                      :x="k.x - 7" :y="k.y - 7" width="14" height="14"
                    />
                    <text :x="k.x + 14" :y="k.y - 1" font-size="11">{{ k.title }}</text>
                    <text class="n-score" :x="k.x + 14" :y="k.y + 12">{{ k.score }}</text>
                  </g>
                </template>
                <template v-if="kgBig.root">
                  <rect class="root" :x="kgBig.root.x - 12" :y="kgBig.root.y - 12" width="24" height="24" />
                  <text class="root-label" :x="kgBig.root.x" :y="kgBig.root.y - 22" text-anchor="middle">{{ kgBig.root.label }}</text>
                </template>
              </svg>
            </div>
          </div>
          <div class="kg-legend">
            <span><i style="background:var(--ink)"></i>掌握</span>
            <span><i style="border:1.5px dashed var(--seal)"></i>薄弱</span>
            <span><i style="background:var(--ink-12)"></i>未覆盖</span>
            <span style="margin-left:auto">点击节点看题目详情</span>
          </div>
          <!-- 节点详情：题干 + 答案 + 得分记录 -->
          <div v-if="kgSelected" class="dm-kg-detail">
            <h3>{{ kgSelected.stem }}</h3>
            <div class="q-scores">
              {{ kgSelected.tech_stack.toUpperCase() }} · {{ kgSelected.group }} ·
              <span class="dm-stamp" :class="kgSelected.status">{{ STATUS_CN[kgSelected.status] }}</span>
            </div>
            <div class="q-answer">{{ kgSelected.answer }}</div>
            <div class="q-scores">
              得分记录：
              <template v-if="kgSelected.recent_scores.length">
                <template v-for="(s, i) in kgSelected.recent_scores" :key="i">
                  {{ s.date }} <b :class="{ bad: s.score < 60 }">{{ Math.round(s.score) }}</b>{{ i < kgSelected.recent_scores.length - 1 ? ' · ' : '' }}
                </template>
              </template>
              <template v-else>暂无（尚未作答）</template>
            </div>
          </div>
        </template>

        <!-- 放大 · 今日建议：完整清单 + 助手安排 -->
        <template v-else-if="modalKey === 'suggest'">
          <div class="dm-sec-label">薄弱题（按得分升序，越低越优先）</div>
          <ul class="dm-suggest">
            <li v-for="q in suggestWeak" :key="q.question_id">
              <span class="d">{{ Math.round(q.latest_score) }} 分</span>
              <span class="t">{{ q.stem }}<small>{{ q.reason }}</small></span>
              <span class="s">{{ q.tech_stack.toUpperCase() }}</span>
            </li>
            <li v-if="!suggestWeak.length"><span class="d">OK</span><span class="t">暂无薄弱题<small>所有答过的题都已及格，保持节奏</small></span><span class="s">—</span></li>
          </ul>
          <div class="dm-sec-label">待补答队列</div>
          <ul class="dm-suggest">
            <li v-for="(r, i) in suggestRetry" :key="'rq' + i">
              <span class="d">待补答</span>
              <span class="t">{{ r.stem }}<small>考核未通过，已入待补答队列，记忆训练中优先重背</small></span>
              <span class="s">{{ (r.tech_stack || '').toUpperCase() }}</span>
            </li>
            <li v-if="!suggestRetry.length"><span class="d">OK</span><span class="t">队列为空<small>没有待补答的题</small></span><span class="s">—</span></li>
          </ul>
          <button class="dm-plan-btn" :disabled="planLoading" @click="askPlan">
            {{ planLoading ? '助手筹划中 …' : '问问助手怎么安排' }}
          </button>
          <div v-if="planReply" class="dm-plan-reply">
            <span class="who">智能助理 · 复习计划</span>{{ planReply }}
          </div>
        </template>

        <!-- 放大 · API 消耗：三指标切换柱状图 + 按模型明细 -->
        <template v-else-if="modalKey === 'usage'">
          <div class="kg-tabs">
            <button
              v-for="t in USAGE_METRICS" :key="t.key"
              class="kg-tab" :class="{ active: t.key === usageMetric }"
              @click="usageMetric = t.key"
            >{{ t.label }}</button>
          </div>
          <svg class="chart-line" :viewBox="`0 0 ${UW2} ${UH2}`" style="width:100%;height:auto">
            <!-- Y 轴三档网格线 + 刻度 -->
            <template v-for="g in [0, 0.5, 1]" :key="g">
              <line
                :x1="upad2" :y1="UH2 - upad2 - g * (UH2 - upad2 * 2)"
                :x2="UW2 - upad2" :y2="UH2 - upad2 - g * (UH2 - upad2 * 2)"
                stroke="rgba(25,25,25,.12)" stroke-width="1" :stroke-dasharray="g ? '2 4' : undefined"
              />
              <text
                :x="upad2 - 8" :y="UH2 - upad2 - g * (UH2 - upad2 * 2) + 4"
                text-anchor="end" font-family="var(--mono)" font-size="9" fill="rgba(25,25,25,.45)"
              >{{ usageAxisFmt(usageBig.max * g) }}</text>
            </template>
            <!-- X 轴：每 5 天一个 MM-DD 标签 -->
            <text
              v-for="b in usageBig.bars" :key="'x' + b.i"
              v-show="b.i % 5 === 0 || b.i === usageBig.bars.length - 1"
              :x="b.x + 9" :y="UH2 - 8" text-anchor="middle"
              font-family="var(--mono)" font-size="9" fill="rgba(25,25,25,.45)"
            >{{ b.date.slice(5) }}</text>
            <!-- 柱条（墨色，悬停看精确值） -->
            <template v-for="b in usageBig.bars" :key="b.i">
              <rect v-if="b.h > 0" :x="b.x" :y="b.y" width="18" :height="b.h" fill="var(--ink)">
                <title>{{ b.date }} · {{ usageMetric === 'cost' ? '¥' + b.v.toFixed(4) : fmtInt(b.v) }}</title>
              </rect>
            </template>
          </svg>
          <div v-if="!usageBig.bars.some(b => b.h > 0)" class="dm-empty" style="margin-top:10px">近 30 天暂无 LLM 调用记录</div>
          <div class="dm-sec-label" style="margin-top:22px">按模型（全量）</div>
          <table class="dm-table">
            <thead><tr><th>模型</th><th>Provider</th><th>请求次数</th><th>Tokens</th><th>估算花费</th></tr></thead>
            <tbody>
              <tr v-for="m in modalData.usage.models" :key="m.model">
                <td class="mono">{{ m.model }}</td>
                <td class="mono dim">{{ m.provider.toUpperCase() }}</td>
                <td class="mono">{{ fmtInt(m.requests) }}</td>
                <td class="mono">{{ fmtInt(m.tokens) }}</td>
                <td class="mono">{{ m.priced ? '¥' + m.cost.toFixed(4) : '套餐额度' }}</td>
              </tr>
              <tr v-if="!modalData.usage.models.length"><td colspan="5" class="dim">暂无调用记录</td></tr>
            </tbody>
          </table>
          <div class="iv-note" style="margin-top:12px">// 花费按后端单价表估算：DeepSeek 分高峰（9:00–12:00、14:00–18:00）与空闲时段，缓存命中价另计；Kimi 为套餐额度只记 token 不计价；实际账单以平台为准</div>
        </template>
      </template>
    </DashboardModal>

    <!-- 录入题库 -->
    <ImportPanel v-if="showImport" @close="showImport = false" @done="onImported" />
  </section>
</template>
