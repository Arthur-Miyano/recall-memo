<script setup>
// 屏幕一：首页 · 档案抽屉（模式选择）
// 职责：整页 flex 布局 + 三个文件夹抽屉手风琴
// 数据流：GET /api/home/summary → homeSummary；请求失败回退 mock/home.js（console.warn，不白屏）
// 动效：
//   - 抽屉开合用 grid-template-rows 0fr→1fr 过渡（.drawer.open）
//   - 手风琴：纯点击切换，同时只展开一个，默认展开 NO.01 记忆训练
//   - 文件夹凸舌随 hover/open 上移（CSS .drawer::before）
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { homeSummary as mockHome } from '../mock/home'
import { getHomeSummary } from '../api'
import { useSessionStore } from '../stores/session'

const router = useRouter()
const sessionStore = useSessionStore()
const canResumeMemorize = computed(() => sessionStore.canResumeMemorize)
// 先用 mock 渲染骨架，真实数据到位后整体替换
const data = ref(mockHome)

// openIdx：当前展开的抽屉下标；null 表示全部收起
const openIdx = ref(0)
// 每个抽屉内各可选项组的单选状态：[抽屉][组] = 选中下标
const optSel = ref(mockHome.drawers.map(d => d.optGroups.map(g => g.on)))

onMounted(async () => {
  try {
    data.value = await getHomeSummary()
    optSel.value = data.value.drawers.map(d => d.optGroups.map(g => g.on))
  } catch (e) {
    console.warn('[home] 后端不可用，回退 mock 数据：', e.message)
  }
})

// 手风琴切换：点击已展开的抽屉则收起，否则只展开被点击的那个
function toggleDrawer(i) {
  openIdx.value = openIdx.value === i ? null : i
}

// CTA 跳转：把抽屉里选的题量/技术栈带过去
const MEMORIZE_COUNTS = [3, 5, 7]
const INTERVIEW_COUNTS = [3, 4, 5]
// 记忆训练题量自由输入（1~20）：非空时优先于胶囊选择，并取消胶囊高亮
const customCount = ref('')
// 取选中项的 value：技术栈组 options 为 [{value, label}]（对象），题量组仍是字符串数组（原样透传）
function optValue(g, oi) {
  const o = g.options[oi]
  return (o && typeof o === 'object') ? o.value : o
}
// 可选项胶囊：组内单选；点记忆训练题量胶囊时清空自由输入
function pickOpt(di, gi, oi) {
  optSel.value[di][gi] = oi
  if (di === 0 && gi === 1) customCount.value = ''
}
function onCountInput() {
  if (customCount.value !== '') optSel.value[0][1] = -1
}
function memorizeCount() {
  const n = parseInt(customCount.value, 10)
  if (!Number.isNaN(n)) return Math.min(20, Math.max(1, n))
  return MEMORIZE_COUNTS[optSel.value[0][1]] ?? 3
}
function go(di) {
  if (di === 0) {
    // NO.01 记忆训练：组 0 = 技术栈（取选中项 value），组 1 = 题量（胶囊或自由输入）
    // fresh 时间戳：每次点击「开始记忆」都开新一轮抽题；切页返回（无新 fresh）则恢复原题
    const groups = data.value.drawers[0].optGroups
    router.push({
      path: '/memorize',
      query: {
        stack: optValue(groups[0], optSel.value[0][0]),
        count: memorizeCount(),
        fresh: String(Date.now()),
      },
    })
  } else if (di === 1) {
    const groups = data.value.drawers[1].optGroups
    router.push({
      path: '/interview',
      query: {
        stack: optValue(groups[0], optSel.value[1][0]),
        count: INTERVIEW_COUNTS[optSel.value[1][1]],
      },
    })
  } else {
    router.push({ path: '/memorize', query: { mode: 'review', fresh: String(Date.now()) } })
  }
}

function resumeMemorize() {
  router.push({
    path: '/memorize',
    query: sessionStore.memorize?.mode === 'review' ? { mode: 'review' } : {},
  })
}
</script>

<template>
  <section class="screen active" id="s-home">
    <div class="home-head">
      <div class="meta-row">
        <span>RECALL — 记忆助手 / LOCAL</span>
        <span id="home-date">{{ data.date }}</span>
      </div>
      <h1 class="home-title">今天，<br>进行哪一场<em>面试</em>？</h1>
      <p class="home-sub">{{ data.sub }}</p>
    </div>

    <div class="drawers">
      <div
        v-for="(d, di) in data.drawers"
        :key="d.idx"
        class="drawer"
        :class="{ open: openIdx === di }"
      >
        <div class="drawer-row" @click="toggleDrawer(di)">
          <span class="drawer-idx">{{ d.idx }}</span>
          <span class="drawer-name">{{ d.name }}</span>
          <span class="drawer-hint">{{ d.hint }}</span>
        </div>
        <div class="drawer-body"><div>
          <div class="drawer-stats">
            <div class="stat" v-for="s in d.stats" :key="s.k">
              <div class="k">{{ s.k }}</div>
              <div class="v" :style="s.seal ? 'color:var(--seal)' : ''">{{ s.v }}<small v-if="s.small">{{ s.small }}</small></div>
            </div>
          </div>
          <!-- 可选项组：记忆训练 2 组（技术栈 + 题量），面试模拟 2 组（技术栈 + 题量） -->
          <div
            v-if="d.optGroups.length"
            class="drawer-cta"
            :style="d.optGroups.length > 1
              ? 'border-top:1px solid var(--ink-12);padding-top:20px;flex-direction:column;align-items:flex-start;gap:14px'
              : 'border-top:1px solid var(--ink-12);padding-top:20px'"
          >
            <div class="opt-group" v-for="(g, gi) in d.optGroups" :key="g.label">
              <span class="opt-label">{{ g.label }}</span>
              <button
                v-for="(o, oi) in g.options"
                :key="optValue(g, oi)"
                class="opt"
                :class="[g.seal && 'opt--seal', { on: optSel[di][gi] === oi }]"
                @click.stop="pickOpt(di, gi, oi)"
              >{{ (o && typeof o === 'object') ? o.label : o }}</button>
              <!-- 记忆训练题量：胶囊之外的自由输入（1~20 题） -->
              <input
                v-if="di === 0 && gi === 1"
                v-model="customCount"
                class="opt opt-count"
                type="number" min="1" max="20" step="1"
                placeholder="自定义"
                title="自由输入 1~20 题"
                @click.stop
                @input="onCountInput"
              >
            </div>
          </div>
          <div class="drawer-cta">
            <div class="resume-actions">
              <button
                v-if="di === 0 && canResumeMemorize"
                class="btn btn--ghost"
                @click="resumeMemorize"
              >继续上次记忆 →</button>
              <button class="btn" @click="go(di)">{{ di === 0 && canResumeMemorize ? '开始新一轮 →' : d.cta }}</button>
            </div>
            <span class="iv-note">{{ d.note }}</span>
          </div>
        </div></div>
      </div>
    </div>

    <div class="home-foot">
      <span>RECALL · 记忆助手 — 八股面试训练</span>
      <span>FIG.01 — MODE SELECT</span>
    </div>
  </section>
</template>

<style scoped>
/* 技术栈 label 后端给的是显示名（如 "Python"），全大写效果交给 CSS，不再在数据里硬写大写 */
.opt--seal { text-transform: uppercase; }
.resume-actions { display: flex; flex-wrap: wrap; gap: 10px; }
/* 题量自由输入框：与胶囊同风格，圆角描边 */
.opt-count { width: 96px; padding: 5px 14px; cursor: text; }
.opt-count:focus { border-color: var(--ink); color: var(--ink); outline: none; }
</style>
