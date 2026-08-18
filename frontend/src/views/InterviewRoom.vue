<script setup>
// 屏幕二：面试答题（限时作答，无即时反馈）
// 职责：倒计时 + 追问标 + 稿纸输入框 + 提交后「已记录」印章态
// 数据流（真实接口，失败回退 mock/interview.js 并 console.warn）：
//   POST /api/sessions {mode: interview}   —— 抽题并直接返回第一题（含追问标识/出题时间）
//   POST /api/sessions/{id}/answer         —— 只回执「已记录」，评分留待终局复盘
//   POST /api/sessions/{id}/skip           —— 跳过判负并进待补答队列
//   全部答完 → 复盘页 /review
// 动效：
//   - 倒计时每秒递减，顶部细线宽度同步；归零时显示「已超时」
//   - 提交后答案区隐藏，已记录面板 screenIn + 印章 stampIn 盖下
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { interviewSession as iv } from '../mock/interview'
import { createSession, submitAnswer, skipQuestion } from '../api'
import { useSessionStore } from '../stores/session'

const route = useRoute()
const router = useRouter()
const store = useSessionStore()

const TOTAL_SEC = 120            // 每题限时 2:00
const useMock = ref(false)
const loadError = ref('')        // 创建面试会话失败的业务错误（空题库/LLM 不可用）：明确提示，不用 mock 冒充
const sessionId = ref(null)
const topLeft = ref(iv.topLeft)
const progressTag = ref(iv.progressTag)
const question = ref(iv.question)
const followTag = ref(iv.followTag)
const answerText = ref('')
const answerEl = ref(null)   // 答题框（自动撑高 / 换题复位）

const sec = ref(iv.leftSec)      // 剩余秒数
const recorded = ref(false)      // 是否已提交（显示已记录印章）
const busy = ref('')
const lastPayload = ref(null)    // 最近一次 answer/skip 的回执（含 next_question / finished）
let askedAt = null               // 当前题出题时间（ISO 串）
let startedAt = null             // 用户开始作答时间
let timer = null

// 倒计时文字：m:ss；归零显示「已超时」
const timerText = computed(() => {
  const mm = Math.floor(sec.value / 60)
  const ss = String(sec.value % 60).padStart(2, '0')
  return `${mm}:${ss}`
})
// 顶部细线宽度：剩余 / 总限时
const lineWidth = computed(() => (sec.value / TOTAL_SEC * 100) + '%')
const over = computed(() => sec.value <= 0)

// 剩余秒数：以 asked_at 为基准（无 asked_at 的 mock 态用演示值）
function resetTimer(q) {
  if (q?.asked_at) {
    askedAt = q.asked_at
    const elapsed = (Date.now() - new Date(askedAt).getTime()) / 1000
    sec.value = Math.max(0, Math.round(TOTAL_SEC - elapsed))
  } else {
    askedAt = null
    sec.value = iv.leftSec
  }
}

// 应用一道新题到界面
function applyQuestion(q) {
  question.value = q.variant_stem
  progressTag.value = `第 ${q.progress} 题`
  followTag.value = q.followup ? `追问 ${q.followup}` : '独立题'
  recorded.value = false
  answerText.value = ''
  if (answerEl.value) answerEl.value.style.height = ''   // 答题框高度复位
  startedAt = null
  resetTimer(q)
}

onMounted(async () => {
  timer = setInterval(() => {
    if (askedAt) {
      const elapsed = (Date.now() - new Date(askedAt).getTime()) / 1000
      sec.value = Math.max(0, Math.round(TOTAL_SEC - elapsed))
    } else {
      sec.value = Math.max(0, sec.value - 1)
    }
  }, 1000)
  const stack = typeof route.query.stack === 'string' ? route.query.stack : null
  const count = Number(route.query.count) || 4
  try {
    const d = await createSession('interview', stack, count)
    sessionId.value = d.session_id
    topLeft.value = `INTERVIEW — ${(stack || 'mixed') === 'mixed' ? '混合场' : String(stack).toUpperCase()} ${d.question_count} 题`
    applyQuestion(d.first_question)
  } catch (e) {
    if (e.isNetwork) {
      // 后端不可达：回退 mock 演示数据（离线角标由 api 层置位）
      console.warn('[interview] 创建面试会话失败（网络），回退 mock 演示数据：', e.message)
      useMock.value = true
    } else {
      // 业务错误（空题库/LLM 不可用等）：明确提示，不用 mock 冒充真题
      console.warn('[interview] 创建面试会话失败：', e.message)
      loadError.value = e.message
    }
  }
})
onUnmounted(() => clearInterval(timer))

// 首次输入视为开始作答（时间压力检测）；答题框随内容自动撑高
function onInput(e) {
  if (!startedAt) startedAt = new Date().toISOString()
  const el = e.target
  el.style.height = 'auto'
  el.style.height = Math.max(260, el.scrollHeight) + 'px'
}

// 提交回答：面试模式只回执「已记录」，不透露对错
async function submit() {
  if (useMock.value) { recorded.value = true; return }
  const text = answerText.value.trim()
  if (!text) return
  busy.value = '记录中…'
  try {
    lastPayload.value = await submitAnswer(sessionId.value, text, startedAt)
    recorded.value = true
  } catch (e) {
    console.warn('[interview] answer 失败：', e.message)
    alert('提交失败：' + e.message)
  } finally {
    busy.value = ''
  }
}

// 跳过本题：判负并进待补答队列
async function skip() {
  if (useMock.value) { recorded.value = true; return }
  busy.value = '记录中…'
  try {
    lastPayload.value = await skipQuestion(sessionId.value)
    recorded.value = true
  } catch (e) {
    console.warn('[interview] skip 失败：', e.message)
    alert('跳过失败：' + e.message)
  } finally {
    busy.value = ''
  }
}

// 下一题 / 全部答完 → 终局复盘
function next() {
  const p = lastPayload.value
  if (!p) return
  if (p.finished) {
    store.lastReviewSessionId = sessionId.value
    router.push({ path: '/review', query: { session_id: sessionId.value } })
  } else {
    applyQuestion(p.next_question)
  }
}
</script>

<template>
  <section class="screen active">
    <div class="iv-wrap">
      <div class="iv-topbar">
        <span>{{ topLeft }}</span>
        <span class="tag">{{ progressTag }}</span>
        <span class="spacer"></span>
        <span>限时开始作答</span>
        <span class="iv-timer" :class="{ over }">{{ over ? '已超时' : timerText }}</span>
      </div>
      <div class="iv-line" :class="{ over }"><i :style="{ width: lineWidth }"></i></div>

      <!-- 创建会话失败的业务错误（空题库/LLM 不可用）：明确提示 + 出口 -->
      <template v-if="loadError">
        <div class="iv-agent">ERROR</div>
        <h2 class="iv-question" style="font-size:22px">无法开始面试</h2>
        <p class="iv-note" style="margin:12px 0 22px">{{ loadError }}</p>
        <div class="iv-actions">
          <button class="btn btn--ghost" @click="router.push('/bank')">去题库看看 →</button>
          <button class="btn" @click="router.push('/')">返回首页 →</button>
        </div>
      </template>

      <template v-else>
      <div class="iv-agent">面试官 AGENT 提问中</div>
      <h2 class="iv-question">{{ question }}</h2>
      <div class="iv-follow"><span class="tag tag--seal">{{ followTag }}</span></div>

      <div v-show="!recorded">
        <textarea ref="answerEl" class="iv-input" :placeholder="iv.placeholder" v-model="answerText" @input="onInput"></textarea>
        <div class="iv-actions">
          <button class="btn" :disabled="!!busy" @click="submit">{{ busy || '提交回答' }}</button>
          <button class="btn btn--ghost" :disabled="!!busy" @click="skip">跳过本题</button>
          <span class="spacer" style="flex:1"></span>
          <span class="iv-note">{{ iv.note }}</span>
        </div>
      </div>

      <div class="iv-recorded" :class="{ show: recorded }">
        <span class="stamp">已 记 录</span>
        <p>ANSWER LOGGED — 评分将于终局复盘时公布</p>
        <button class="btn" @click="next">{{ lastPayload?.finished ? '查看终局复盘 →' : '下一题 →' }}</button>
      </div>
      </template>
    </div>
  </section>
</template>
