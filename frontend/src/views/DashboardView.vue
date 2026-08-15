<script setup>
// 屏幕四：仪表盘（背诵档案台）
// 职责：日历热力 / 7 天趋势阶梯折线 / 各栈正确率像素柱 / 知识图谱 / 今日建议 / 模型密钥设置
// 数据流（真实接口，任一失败回退 mock/dashboard.js 并 console.warn）：
//   GET /api/stats/overview     —— 各栈正确率、覆盖度
//   GET /api/stats/daily?days=N —— 日历热力（28 天）与 7 天趋势、连续打卡
//   GET /api/bank/overview      —— 知识图谱节点状态 + 今日建议
// 图表说明：折线与知识图谱为手绘 SVG（图纸感直角转折、像素方块节点），
//   有意不用 ECharts —— 像素美学是设计的一部分
import { ref, computed, onMounted } from 'vue'
import SettingsPanel from '../components/SettingsPanel.vue'
import { dashboard as mockDb } from '../mock/dashboard'
import { getStatsOverview, getStatsDaily, getBankOverview } from '../api'

// 整体数据：先渲染 mock 骨架，真实数据到位后逐块替换
const db = ref(mockDb)

const WEEKDAYS_CN = ['日', '一', '二', '三', '四', '五', '六']
// 知识图谱根节点预设坐标（viewBox 440×320），按技术栈顺序循环取用
const ROOT_POS = [{ x: 80, y: 70 }, { x: 320, y: 70 }, { x: 200, y: 260 }, { x: 80, y: 260 }, { x: 360, y: 260 }]
// cell.status → 图谱节点状态
const CELL2NODE = { done: 'mastered', weak: 'weak', todo: 'todo' }

onMounted(async () => {
  try {
    const [ov, daily28, daily7, bank] = await Promise.all([
      getStatsOverview(), getStatsDaily(28), getStatsDaily(7), getBankOverview(),
    ])
    // 连续打卡：从今天往前数有答题的天数
    let streak = 0
    for (let i = daily7.items.length - 1; i >= 0; i--) {
      if (daily7.items[i].total_count > 0) streak++
      else break
    }
    const next = {
      headMeta: [
        `已覆盖 ${ov.covered} / ${ov.total_questions} 题 · 连续打卡 ${streak} 天`,
        `数据截至 ${new Date().toLocaleDateString('zh-CN')}`,
      ],
      // 日历热力：0→0 级，1→l1，2→l2，3→l3，≥4→l4
      calendar: daily28.items.map(d => Math.min(d.total_count, 4)),
      trend: {
        values: daily7.items.map(d => d.total_count),
        days: daily7.items.map(d => WEEKDAYS_CN[new Date(d.date + 'T00:00:00').getDay()]),
        max: Math.max(...daily7.items.map(d => d.total_count), 1),
      },
      accuracy: Object.entries(ov.per_stack).map(([name, s]) => ({
        name: name.toUpperCase(),
        pct: s.pass_rate == null ? 0 : Math.round(s.pass_rate * 100),
      })),
      graph: buildGraph(bank),
      suggestions: buildSuggestions(bank),
      settings: mockDb.settings, // 设置面板自行请求真实接口，这里仅占位
    }
    db.value = next
  } catch (e) {
    console.warn('[dashboard] 统计数据获取失败，回退 mock 数据：', e.message)
  }
})

// 知识图谱：技术栈根节点 + 每题一个子节点（围绕根节点扇形排布）
function buildGraph(bank) {
  const roots = []
  const kids = {}
  bank.stacks.forEach((stack, si) => {
    const pos = ROOT_POS[si % ROOT_POS.length]
    const label = stack.name.toUpperCase()
    roots.push({ x: pos.x, y: pos.y, label })
    kids[label] = []
    let i = 0
    stack.groups.forEach(g => g.cells.forEach(c => {
      kids[label].push({
        x: Math.min(Math.max(pos.x - 50 + (i % 3) * 60, 20), 420),
        y: Math.min(pos.y + 60 + Math.floor(i / 3) * 50, 310),
        t: (c.label || c.tip.split(' · ')[0]).slice(0, 8),
        s: CELL2NODE[c.status] || 'todo',
      })
      i++
    }))
  })
  return { roots, kids }
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

// ---- 知识图谱：根-子连线与节点展平 ----
const kgEdges = computed(() => {
  const edges = []
  db.value.graph.roots.forEach(r => {
    (db.value.graph.kids[r.label] || []).forEach(k => edges.push({ x1: r.x, y1: r.y, x2: k.x, y2: k.y }))
  })
  return edges
})
const kgNodes = computed(() => {
  const nodes = []
  db.value.graph.roots.forEach(r => nodes.push(...(db.value.graph.kids[r.label] || [])))
  return nodes
})
// 正确率像素柱：pct → 10 格
function accCells(p) { return Math.round(p / 10) }
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
        <!-- 日历热力格 -->
        <div class="db-panel">
          <h2>每日背诵记录 <span class="n">FIG.04-A</span></h2>
          <div class="cal">
            <i v-for="(v, i) in db.calendar" :key="i" :class="v ? 'l' + v : ''"></i>
          </div>
          <div class="cal-legend">少 <i style="background:var(--ink-12)"></i><i style="background:rgba(25,25,25,.55)"></i><i style="background:var(--ink)"></i> 多</div>
        </div>
        <!-- 近 7 天答题趋势：阶梯折线 -->
        <div class="db-panel">
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
        </div>
        <!-- 各技术栈正确率：像素柱 -->
        <div class="db-panel">
          <h2>各技术栈正确率 <span class="n">FIG.04-C</span></h2>
          <div class="acc-row" v-for="a in db.accuracy" :key="a.name">
            <span class="name">{{ a.name }}</span>
            <div class="pixbar">
              <i v-for="n in 10" :key="n" :class="{ off: n > accCells(a.pct) }"></i>
            </div>
            <span class="pct">{{ a.pct }}%</span>
          </div>
        </div>
        <!-- 模型与密钥配置 -->
        <SettingsPanel />
      </div>

      <div style="display:flex;flex-direction:column;gap:28px">
        <!-- 知识图谱 -->
        <div class="db-panel">
          <h2>知识图谱 <span class="n">FIG.04-D</span></h2>
          <svg class="kg" viewBox="0 0 440 320">
            <!-- 根-子连线 -->
            <line
              v-for="(e, i) in kgEdges" :key="'e' + i"
              class="lk" :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
            />
            <!-- 知识点节点（mastered/weak/todo） -->
            <template v-for="(k, i) in kgNodes" :key="'n' + i">
              <rect :class="'node-' + k.s" :x="k.x - 7" :y="k.y - 7" width="14" height="14" />
              <text :x="k.x + 12" :y="k.y + 4">{{ k.t }}</text>
            </template>
            <!-- 技术栈根节点 -->
            <template v-for="r in db.graph.roots" :key="'r' + r.label">
              <rect class="root" :x="r.x - 11" :y="r.y - 11" width="22" height="22" />
              <text class="root-label" :x="r.x" :y="r.y - 20" text-anchor="middle">{{ r.label }}</text>
            </template>
          </svg>
          <div class="kg-legend">
            <span><i style="background:var(--ink)"></i>掌握</span>
            <span><i style="border:1.5px dashed var(--seal)"></i>薄弱</span>
            <span><i style="background:var(--ink-12)"></i>未覆盖</span>
          </div>
        </div>
        <!-- 今日建议背诵 -->
        <div class="db-panel">
          <h2>今日建议背诵 <span class="n">FIG.04-E</span></h2>
          <ul class="suggest">
            <li v-for="(sg, i) in db.suggestions" :key="i">
              <span class="d">{{ sg.d }}</span><span class="t">{{ sg.t }}</span><span class="s">{{ sg.s }}</span>
            </li>
            <li v-if="!db.suggestions.length"><span class="d">OK</span><span class="t">暂无薄弱题，保持节奏</span><span class="s">—</span></li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>
