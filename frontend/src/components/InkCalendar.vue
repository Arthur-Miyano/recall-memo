<script setup>
// 通用墨水月历组件（纸墨美学：宋体月标题 + mono 标注 + 墨色分档格子）
// 数据流（纯展示组件，不自行拉取接口，父组件喂数据）：
//   props.items   —— [{ date:'YYYY-MM-DD', total_count:n }]，可覆盖多月
//                     （建议父组件一次拉 90 天：GET /api/stats/daily?days=90，前端按月切换）
//   props.details —— { 'YYYY-MM-DD': [records] }，可选；
//                     records: { mode, title, score, is_retry, skipped }
//                     （来自 GET /api/stats/daily-detail?days=90，只含有答题的日期）
//                     传入后点击有记录的日期格子，在月历下方展开当天逐题明细（低分红字）
// 交互：
//   ← / → 翻月，范围钳制在「数据最早月 ~ 当前月」，不翻进全空的过去/未来
//   格子等级沿用既有 0~4 逻辑：total_count 0→空白，1/2/3→l1~l3，≥4→l4
//   今天：印章红细描边；悬停 title 显示「M月D日 · N 题」
import { ref, computed } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },   // /api/stats/daily 的 items（日期升序）
  details: { type: Object, default: null },    // date → records；null 时格子不可点
})

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'] // 周一打头

// 本地日期 → 'YYYY-MM-DD'（与后端 daily 接口的本地日期口径一致，不用 toISOString 防时区偏一天）
function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const now = new Date()
const year = ref(now.getFullYear())
const month = ref(now.getMonth())   // 0-based

// date → total_count
const countMap = computed(() => {
  const m = {}
  for (const it of props.items) m[it.date] = it.total_count
  return m
})

const todayStr = fmtDate(now)
const nowKey = todayStr.slice(0, 7)                       // 当前月 'YYYY-MM'
const curKey = computed(() => `${year.value}-${String(month.value + 1).padStart(2, '0')}`)
// 数据覆盖的最早月（items 升序，取第一条）；无数据时钳在当前月
const oldestKey = computed(() => (props.items.length ? props.items[0].date.slice(0, 7) : nowKey))
const canPrev = computed(() => curKey.value > oldestKey.value)
const canNext = computed(() => curKey.value < nowKey)

function prevMonth() {
  if (!canPrev.value) return
  if (month.value === 0) { year.value--; month.value = 11 } else month.value--
}
function nextMonth() {
  if (!canNext.value) return
  if (month.value === 11) { year.value++; month.value = 0 } else month.value++
}

const monthTitle = computed(() => `${year.value} 年 ${month.value + 1} 月`)

// 当月格子：前导空格（周一打头）+ 每日格子
const cells = computed(() => {
  const first = new Date(year.value, month.value, 1)
  const lead = (first.getDay() + 6) % 7          // 周一打头的前导空格数
  const days = new Date(year.value, month.value + 1, 0).getDate()
  const out = Array.from({ length: lead }, () => null)
  for (let d = 1; d <= days; d++) {
    const date = `${curKey.value}-${String(d).padStart(2, '0')}`
    const count = countMap.value[date] || 0
    out.push({
      date, day: d, count,
      lvl: Math.min(count, 4),                    // 沿用既有 0~4 等级逻辑
      isToday: date === todayStr,
      title: `${month.value + 1}月${d}日 · ${count} 题`,
    })
  }
  return out
})

// ---- 点击日期展开当天明细（仅传了 details 且有记录时可点） ----
const sel = ref('')
const selRecords = computed(() => (props.details && sel.value ? props.details[sel.value] || [] : []))
function pick(cell) {
  if (!props.details) return
  if (!props.details[cell.date]) return
  sel.value = sel.value === cell.date ? '' : cell.date   // 再点一次收起
}
</script>

<template>
  <div class="inkcal">
    <div class="inkcal-head">
      <button class="inkcal-nav" :disabled="!canPrev" title="上一月" @click="prevMonth">←</button>
      <span class="inkcal-title">{{ monthTitle }}</span>
      <button class="inkcal-nav" :disabled="!canNext" title="下一月" @click="nextMonth">→</button>
    </div>
    <div class="inkcal-grid">
      <span v-for="w in WEEKDAYS" :key="w" class="inkcal-wd">{{ w }}</span>
      <template v-for="(cell, i) in cells" :key="i">
        <span v-if="!cell" class="inkcal-day empty"></span>
        <span
          v-else
          class="inkcal-day"
          :class="[
            cell.lvl ? 'l' + cell.lvl : '',
            { today: cell.isToday, sel: cell.date === sel, has: details && details[cell.date] },
          ]"
          :title="cell.title"
          @click="pick(cell)"
        >{{ cell.day }}</span>
      </template>
    </div>
    <!-- 当天明细：模式 + 题目 + 补答/跳过标记 + 得分（低分印章红），复用 .dm-dayhead/.dm-rec -->
    <div v-if="sel && selRecords.length" class="inkcal-detail">
      <div class="dm-dayhead"><span>{{ sel }}</span><span class="cnt">{{ selRecords.length }} 题</span></div>
      <div class="dm-rec" v-for="(r, i) in selRecords" :key="i">
        <span class="mode">{{ r.mode }}</span>
        <span class="t">{{ r.title }}</span>
        <span v-if="r.is_retry" class="tag">补答</span>
        <span v-if="r.skipped" class="tag">跳过</span>
        <span class="score" :class="{ bad: r.score != null && r.score < 60 }">
          {{ r.score == null ? '—' : Math.round(r.score) }}
        </span>
      </div>
    </div>
  </div>
</template>
