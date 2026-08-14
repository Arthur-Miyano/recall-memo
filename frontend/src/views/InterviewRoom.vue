<script setup>
// 屏幕二：面试答题（限时作答，无即时反馈）
// 职责：倒计时 + 追问标 + 稿纸输入框 + 提交后「已记录」印章态
// 数据流：mock/interview.js → interviewSession（未来 GET /api/interview/session/current）
// 动效：
//   - 倒计时每秒递减，顶部细线宽度同步；归零时闪「已超时」并重置（与原型演示一致）
//   - 提交后答案区隐藏，已记录面板 screenIn + 印章 stampIn 盖下
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { interviewSession as iv } from '../mock/interview'

const sec = ref(iv.leftSec)      // 剩余秒数
const recorded = ref(false)      // 是否已提交（显示已记录印章）
let timer = null

// 倒计时文字：m:ss；归零瞬间显示「已超时」
const timerText = computed(() => {
  const m = Math.floor(sec.value / 60)
  const s = String(sec.value % 60).padStart(2, '0')
  return `${m}:${s}`
})
// 顶部细线宽度：剩余 / 总限时
const lineWidth = computed(() => (sec.value / iv.totalSec * 100) + '%')
// 超时态（红）：仅在归零那一瞬为 true
const over = ref(false)

onMounted(() => {
  // 每秒递减；归零时置 over → 显示「已超时」→ 立即重置回初始秒数（原型演示逻辑）
  timer = setInterval(() => {
    sec.value = Math.max(0, sec.value - 1)
    if (sec.value === 0) {
      over.value = true
      sec.value = iv.leftSec
      over.value = false
    }
  }, 1000)
})
onUnmounted(() => clearInterval(timer))

// 提交回答：隐藏作答区，显示「已记录」印章（面试模式不反馈对错）
function submit() { recorded.value = true }
</script>

<template>
  <section class="screen active">
    <div class="iv-wrap">
      <div class="iv-topbar">
        <span>{{ iv.topLeft }}</span>
        <span class="tag">{{ iv.progressTag }}</span>
        <span class="spacer"></span>
        <span>限时开始作答</span>
        <span class="iv-timer" :class="{ over }">{{ over ? '已超时' : timerText }}</span>
      </div>
      <div class="iv-line" :class="{ over }"><i :style="{ width: lineWidth }"></i></div>

      <div class="iv-agent">面试官 AGENT 提问中</div>
      <h2 class="iv-question">{{ iv.question }}</h2>
      <div class="iv-follow"><span class="tag tag--seal">{{ iv.followTag }}</span></div>

      <div v-show="!recorded">
        <textarea class="iv-input" :placeholder="iv.placeholder"></textarea>
        <div class="iv-actions">
          <button class="btn" @click="submit">提交回答</button>
          <button class="btn btn--ghost">跳过本题</button>
          <span class="spacer" style="flex:1"></span>
          <span class="iv-note">{{ iv.note }}</span>
        </div>
      </div>

      <div class="iv-recorded" :class="{ show: recorded }">
        <span class="stamp">已 记 录</span>
        <p>ANSWER LOGGED — 评分将于终局复盘时公布</p>
        <button class="btn">下一题 →</button>
      </div>
    </div>
  </section>
</template>
