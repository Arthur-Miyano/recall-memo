<script setup>
// 屏幕二：面试答题（限时作答，无即时反馈）
// 职责：倒计时 + 追问标 + 稿纸输入框 + 提交后「已记录」印章态
// 数据流（真实接口，失败回退 mock/interview.js 并 console.warn）：
//   POST /api/sessions {mode: interview}   —— 抽题并直接返回第一题（含追问标识/出题时间）
//   POST /api/sessions/{id}/answer         —— 只回执「已记录」，评分留待终局复盘
//   POST /api/sessions/{id}/skip           —— 跳过判负，不给补答、不进待补答队列
//   全部答完 → 复盘页 /review
// 动效：
//   - 倒计时每秒递减，顶部细线宽度同步；限时只约束「开始作答」，检测到输入即冻结，未开始且归零才显示「已超时」
//   - 提交后答案区隐藏，已记录面板 screenIn + 印章 stampIn 盖下
import { ref, computed, onMounted, onUnmounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { interviewSession as iv } from '../mock/interview'
import {
  createSession, getSessionInfo, getCurrent, submitAnswer, skipQuestion,
  newIdempotencyKey, offline, createRequestScope,
} from '../api'
import { decideRestore, draftStillValid } from '../utils/sessionRecovery'
import { useSessionStore } from '../stores/session'
import { interviewSeconds, interviewTimedOut } from '../utils/interviewTimer'

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
const startedAt = ref(null)      // 用户开始作答时间；必须响应式，超时 computed 才会立即刷新
let answerKey = null             // 当前题「提交回答」的幂等键：失败重试复用，换题时重置
let skipKey = null               // 当前题「跳过」的幂等键，同上
let questionId = null            // 当前题 id：快照恢复时与服务端 current 对账草稿有效性
const scope = createRequestScope()  // 页面级请求域：卸载时取消挂起请求（§8.3）
let timer = null

// 倒计时文字：m:ss；归零显示「已超时」
const timerText = computed(() => {
  const mm = Math.floor(sec.value / 60)
  const ss = String(sec.value % 60).padStart(2, '0')
  return `${mm}:${ss}`
})
// 顶部细线宽度：剩余 / 总限时
const lineWidth = computed(() => (sec.value / TOTAL_SEC * 100) + '%')
// 超时只约束「开始作答」：检测到输入后不限时，不再判超时（需求：2 分钟内必须开始）
const over = computed(() => interviewTimedOut({ startedAt: startedAt.value, seconds: sec.value }))

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
  questionId = q.question_id ?? null
  recorded.value = false
  answerText.value = ''
  answerKey = null                 // 新题新键：上一题的幂等键不复用
  skipKey = null
  if (answerEl.value) answerEl.value.style.height = ''   // 答题框高度复位
  startedAt.value = null
  resetTimer(q)
}

// ---- 会话快照（§8.1）：切页/刷新后先核对服务端状态再恢复，服务端是唯一事实来源 ----
// 本地只保存未提交草稿（draft）与幂等键；题干/进度恢复时从服务端 current 重拉
function saveSnapshot() {
  store.saveInterview({
    sessionId: sessionId.value,
    topLeft: topLeft.value,
    question: question.value,
    progressTag: progressTag.value,
    followTag: followTag.value,
    questionId,
    draft: answerText.value,        // 未提交草稿
    startedAt: startedAt.value,
    recorded: recorded.value,
    lastPayload: lastPayload.value,
    answerKey,
    skipKey,
    useMock: useMock.value,
    finished: recorded.value && !!lastPayload.value?.finished,
  })
}

function restoreSnapshot(snap) {
  sessionId.value = snap.sessionId
  topLeft.value = snap.topLeft
  question.value = snap.question
  progressTag.value = snap.progressTag
  followTag.value = snap.followTag
  questionId = snap.questionId ?? null
  answerText.value = snap.draft || ''
  startedAt.value = snap.startedAt || null
  recorded.value = snap.recorded
  lastPayload.value = snap.lastPayload
  answerKey = snap.answerKey ?? null
  skipKey = snap.skipKey ?? null
  useMock.value = snap.useMock
}

// 进入页面：先查服务端会话状态（唯一事实来源），再决定恢复 / 离线兜底 / 跳复盘 / 重建（§8.1）
async function initSession() {
  const stack = typeof route.query.stack === 'string' ? route.query.stack : null
  const count = Number(route.query.count) || 4
  const snap = store.interview
  if (snap) {
    // demo 快照只在仍离线时恢复展示；后端已恢复则落到下面重建真实会话（§8.2）
    if (snap.useMock) {
      if (offline.value) { restoreSnapshot(snap); return }
    } else if (snap.sessionId) {
      let decision
      try {
        const info = await getSessionInfo(snap.sessionId, { retry: 1, signal: scope.signal })
        decision = decideRestore({ snapshot: snap, serverInfo: info, expectedMode: 'interview' })
      } catch (e) {
        if (scope.signal.aborted) return
        decision = decideRestore({ snapshot: snap, serverError: e, expectedMode: 'interview' })
      }
      if (decision.action === 'restore') {
        restoreSnapshot(snap)
        if (!(snap.recorded && snap.lastPayload)) {
          // 未提交态：以服务端 current 为准刷新题目与计时；草稿仅在同题时保留
          try {
            const cur = await getCurrent(snap.sessionId, { retry: 1, signal: scope.signal })
            const draft = snap.draft
            const keepDraft = draftStillValid(cur.question_id, snap.questionId)
            applyQuestion(cur)   // 以服务端为准重置本题（含按 asked_at 重算倒计时）
            if (keepDraft) {
              answerText.value = draft
              startedAt.value = snap.startedAt || null
              answerKey = snap.answerKey ?? null
              skipKey = snap.skipKey ?? null
            }
            // 服务端已推进（提交成功但响应丢失）：草稿已被服务端接收，丢弃本地草稿
          } catch (e) {
            if (scope.signal.aborted) return
            console.warn('[interview] 恢复当前题失败：', e.message)
          }
        }
        saveSnapshot()
        return
      }
      if (decision.action === 'offline') { restoreSnapshot(snap); return }
      if (decision.action === 'finished') {
        // 服务端已生成复盘而本地未收到响应：直接去复盘页，不重复提交（§8.1）
        store.clearInterview()
        store.lastReviewSessionId = snap.sessionId
        router.push({ path: '/review', query: { session_id: snap.sessionId } })
        return
      }
      // restart：快照失效（过期/404/模式冲突），丢弃后落到下面重建
    }
  }
  // 创建新会话
  useMock.value = false
  loadError.value = ''
  try {
    const d = await createSession('interview', stack, count, { signal: scope.signal })
    sessionId.value = d.session_id
    topLeft.value = `INTERVIEW — ${(stack || 'mixed') === 'mixed' ? '混合场' : String(stack).toUpperCase()} ${d.question_count} 题`
    applyQuestion(d.first_question)
  } catch (e) {
    if (scope.signal.aborted) return
    if (e.isNetwork) {
      // 后端不可达：回退 mock 演示数据（离线角标由 api 层置位）
      console.warn('[interview] 创建面试会话失败（网络），回退 mock 演示数据：', e.message)
      useMock.value = true
    } else {
      // 业务错误（空题库/LLM 不可用等）：明确提示，不用 mock 冒充真题
      console.warn('[interview] 创建面试会话失败：', e.message)
      loadError.value = e.message
      return
    }
  }
  saveSnapshot()
}

onMounted(() => {
  timer = setInterval(() => {
    sec.value = interviewSeconds({
      startedAt: startedAt.value,
      askedAt,
      now: Date.now(),
      currentSeconds: sec.value,
      totalSeconds: TOTAL_SEC,
    })
  }, 1000)
  initSession()
})
onBeforeUnmount(() => { if (sessionId.value || useMock.value) saveSnapshot() })
onUnmounted(() => {
  clearInterval(timer)
  scope.cancel()   // 页面卸载：取消挂起请求（AbortError，不置离线标记）
})

// 后端恢复（offline 摘标）后重建真实会话：demo 数据只兜底展示，不当用户数据继续用（§8.2）
watch(offline, (v, prev) => { if (prev && !v && useMock.value) initSession() })

// 首次输入视为开始作答（时间压力检测）；答题框随内容自动撑高
function onInput(e) {
  if (!startedAt.value) startedAt.value = new Date().toISOString()
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
    if (!answerKey) answerKey = newIdempotencyKey()   // 一次提交一个键，失败重试复用
    lastPayload.value = await submitAnswer(sessionId.value, text, startedAt.value, answerKey)
    recorded.value = true
    saveSnapshot()   // 回执落快照：崩溃/切页后据此恢复或跳复盘
  } catch (e) {
    console.warn('[interview] answer 失败：', e.message)
    alert('提交失败：' + e.message)
  } finally {
    busy.value = ''
  }
}

// 跳过本题：判负（不给补答、不进待补答队列）
async function skip() {
  if (useMock.value) { recorded.value = true; return }
  busy.value = '记录中…'
  try {
    if (!skipKey) skipKey = newIdempotencyKey()
    lastPayload.value = await skipQuestion(sessionId.value, skipKey)
    recorded.value = true
    saveSnapshot()
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
    store.clearInterview()   // 面试已结束：清掉快照，复盘页不需要恢复答题现场
    store.lastReviewSessionId = sessionId.value
    const sid = sessionId.value
    sessionId.value = null   // 阻止 onBeforeUnmount 把已结束的会话再回存成快照
    router.push({ path: '/review', query: { session_id: sid } })
  } else {
    applyQuestion(p.next_question)
    saveSnapshot()
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
