// composable：记忆训练会话（恢复 + 题目推进）
// 职责：会话创建 / 恢复决策（§8.1 服务端为唯一事实来源）、快照保存恢复、
//       考核推进（start_quiz / answer）、中断后幂等重放取回评分结果
// 视图（views/MemorizeFlow.vue）只留展示态：单题放大、划句存笔记、答题框自适应、导出卡片
import { ref, computed, watch, onMounted, onBeforeUnmount, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { memorizeSession as m } from '../mock/memorize'
import {
  createSession, getSessionInfo, startQuiz as apiStartQuiz, getCurrent, submitAnswer,
  newIdempotencyKey, offline, createRequestScope,
} from '../api'
import { decideRestore, draftStillValid, shouldResyncMemorize } from '../utils/sessionRecovery'
import { canSubmit, OFFLINE_WRITE_TIP } from '../utils/offlineGuard'
import { useSessionStore } from '../stores/session'

export function useMemorizeSession() {
  const route = useRoute()
  const sessionStore = useSessionStore()

  // ---- mock 兜底态（后端不可用时展示演示数据） ----
  const useMock = ref(false)
  const loadError = ref('')   // 创建会话失败的业务错误（空题库/LLM 不可用等）：明确提示，不用 mock 冒充
  const quizzing = ref(false)   // 是否已进入考核阶段
  const kwShow = ref(false)     // 关键词提示是否展开
  const fbShow = ref(false)     // 即时反馈是否展示

  // ---- 真实会话态 ----
  const sessionId = ref(null)
  const topLeft = ref(m.topLeft)
  const topRight = ref(m.topRight)
  const questions = ref(m.questions)      // 阶段一：{no, title, retry, answer}
  const kwMap = {}                        // question_id → keywords（create_session 返回）
  const quiz = ref({                      // 阶段二当前题
    question: m.quiz.question,
    followTag: m.quiz.followTag,
    keywords: m.quiz.keywords,
  })
  const answerText = ref('')
  const feedback = ref(m.quiz.feedback)   // 即时反馈
  const finished = ref(false)
  const summary = ref(null)               // 全部答完后的本轮总结
  const busy = ref('')                    // '出题中…' / '评分中…' 等加载提示
  let quizKey = null                      // 当前题提交的幂等键：失败重试复用同键，进入下一题时重置
  let quizQid = null                      // 当前考核题的 question_id：恢复时对账草稿是否仍有效
  const scope = createRequestScope()      // 页面级请求域：卸载时取消挂起请求（§8.3）

  // 评分 JSON → 反馈面板结构
  function toFeedback(score, yourAnswer, stdAnswer) {
    return {
      no: 'FEEDBACK — 评分 AGENT',
      title: '本题反馈',
      score: String(score.total),
      dims: [
        { label: '准确性 50%', value: Math.round(score.accuracy), seal: false },
        { label: '逻辑 30%', value: Math.round(score.logic), seal: false },
        { label: '自然度 20%', value: Math.round(score.naturalness), seal: score.is_reciting },
      ],
      comment: '点评：' + (score.comment || '（无点评）'),
      provider: score.provider || '',
      model: score.model || '',
      yourAnswer,
      stdAnswer,
    }
  }

  // ---- 会话快照：开始训练后题目固定，切页再回来原样恢复 ----
  // 只有首页「开始记忆」带新 fresh token 跳转时才重开一轮；其余入口（含浏览器后退）都恢复快照
  function saveSnapshot(fresh) {
    sessionStore.saveMemorize({
      fresh: fresh ?? sessionStore.memorize?.fresh ?? null,
      sessionId: sessionId.value,
      topLeft: topLeft.value,
      topRight: topRight.value,
      questions: questions.value,
      kwMap: { ...kwMap },
      quizzing: quizzing.value,
      quiz: quiz.value,
      quizQid,                        // 当前考核题 id：恢复时与服务端 current 对账
      answerText: answerText.value,   // 未提交草稿（本地恢复的唯一内容，其余以服务端为准）
      feedback: feedback.value,
      fbShow: fbShow.value,
      finished: finished.value,
      summary: summary.value,
      useMock: useMock.value,
      quizKey,                      // 当前题的幂等键：切页再回来重试仍复用同键
    })
  }

  function restoreSnapshot(snap) {
    sessionId.value = snap.sessionId
    topLeft.value = snap.topLeft
    topRight.value = snap.topRight
    questions.value = snap.questions
    Object.assign(kwMap, snap.kwMap)
    quizzing.value = snap.quizzing
    quiz.value = snap.quiz
    quizQid = snap.quizQid ?? null
    answerText.value = snap.answerText
    feedback.value = snap.feedback
    fbShow.value = snap.fbShow
    finished.value = snap.finished
    summary.value = snap.summary
    useMock.value = snap.useMock
    quizKey = snap.quizKey ?? null
  }

  // 应用服务端返回的题目列表到展示阶段（创建会话专用）
  function applyQuestions(d, mode, stack) {
    sessionId.value = d.session_id
    topLeft.value = `${mode === 'review' ? 'RECALL' : 'MEMORIZE'} — ${(d.questions[0]?.tech_stack || stack || 'mixed').toUpperCase()} · 本轮 ${d.questions.length} 题`
    topRight.value = `${d.state} — ${mode === 'review' ? '回忆中' : '记忆中'}`
    questions.value = d.questions.map((q, i) => {
      kwMap[q.question_id] = q.keywords || []
      return { no: `题 ${i + 1} / ${d.questions.length}`, title: q.stem, retry: q.retry, answer: q.answer }
    })
  }

  // 用幂等键重放取回已保存的评分结果（后端重放语义：同键重发返回已存结果，不是重复提交）
  async function replayAnswer(snap) {
    const d = await submitAnswer(sessionId.value, snap.answerText, undefined, snap.quizKey)
    feedback.value = toFeedback(d.score, snap.answerText, d.standard_answer)
    fbShow.value = true
    if (d.finished) {
      finished.value = true
      summary.value = d.summary
    } else {
      const nx = d.next_question
      quiz.value = {
        question: nx.variant_stem,
        followTag: `考核 ${nx.progress} · 已打乱`,
        keywords: kwMap[nx.question_id] || [],
      }
      quizQid = nx.question_id
    }
  }

  // 考核中恢复：以服务端 current 为准刷新当前题；草稿仅在同题时保留
  async function resyncCurrent(snap, serverInfo) {
    if (!shouldResyncMemorize({ snapshot: snap, serverInfo })) return
    if (snap.fbShow) return   // 已出反馈：纯展示态，原样恢复
    try {
      const cur = await getCurrent(sessionId.value, { retry: 1, signal: scope.signal })
      quizzing.value = true
      quiz.value = {
        question: cur.variant_stem,
        followTag: `考核 ${cur.progress} · 已打乱`,
        keywords: cur.keywords || [],
      }
      if (draftStillValid(cur.question_id, snap.quizQid)) return   // 同一题：保留本地未提交草稿
      // 服务端已推进而本地未收到反馈：重放幂等键取回结果
      if (snap.quizKey && snap.answerText) { await replayAnswer(snap); return }
      // 无法对账：以服务端为准，丢弃本地草稿
      answerText.value = ''
      quizKey = null
      quizQid = cur.question_id
    } catch (e) {
      if (scope.signal.aborted) return
      console.warn('[memorize] 恢复考核进度失败：', e.message)
    }
  }

  // 进入页面：先核对服务端会话状态（唯一事实来源），再决定恢复 / 离线兜底 / 重建（§8.1）
  async function initSession() {
    const mode = route.query.mode === 'review' ? 'review' : 'memorize'
    const count = Number(route.query.count) || 3
    const stack = typeof route.query.stack === 'string' ? route.query.stack : null
    const fresh = typeof route.query.fresh === 'string' ? route.query.fresh : null
    // 有快照且本次不是「新的开始」（无 fresh 或 fresh 与快照一致）→ 走恢复决策
    const snap = sessionStore.memorize
    if (snap && (!fresh || snap.fresh === fresh)) {
      // demo 快照只在仍离线时恢复展示；后端已恢复则落到下面重建真实会话（§8.2）
      if (snap.useMock) {
        if (offline.value) { restoreSnapshot(snap); return }
      } else if (snap.sessionId) {
        let decision
        let serverInfo
        try {
          serverInfo = await getSessionInfo(snap.sessionId, { retry: 1, signal: scope.signal })
          decision = decideRestore({ snapshot: snap, serverInfo, expectedMode: mode })
        } catch (e) {
          if (scope.signal.aborted) return
          decision = decideRestore({ snapshot: snap, serverError: e, expectedMode: mode })
        }
        if (decision.action === 'restore') {
          restoreSnapshot(snap)
          await resyncCurrent(snap, serverInfo)
          saveSnapshot()
          return
        }
        if (decision.action === 'offline') { restoreSnapshot(snap); return }
        if (decision.action === 'finished' && snap.quizKey && snap.answerText) {
          // 服务端已完成而本地未收到响应：幂等重放取回结果
          try {
            restoreSnapshot(snap)
            await replayAnswer(snap)
            saveSnapshot()
            return
          } catch (e) {
            console.warn('[memorize] 重放最后一次提交失败，重建会话：', e.message)
          }
        }
        // restart / 重放失败：快照失效（过期/404/模式冲突），丢弃后落到下面重建
      }
    }
    // 创建新会话
    useMock.value = false
    loadError.value = ''
    try {
      const d = await createSession(mode, stack, count, { signal: scope.signal })
      applyQuestions(d, mode, stack)
    } catch (e) {
      if (scope.signal.aborted) return
      if (e.isNetwork) {
        // 后端不可达：回退 mock 演示数据（离线角标由 api 层置位）
        console.warn('[memorize] 创建会话失败（网络），回退 mock 演示数据：', e.message)
        useMock.value = true
      } else {
        // 业务错误（空题库/LLM 不可用等）：明确提示，不用 mock 冒充真题；
        // 且不保存快照——下次进入重新尝试创建会话
        console.warn('[memorize] 创建会话失败：', e.message)
        loadError.value = e.message
        return
      }
    }
    saveSnapshot(fresh)
  }

  onMounted(initSession)

  // 后端恢复（offline 摘标）后重建真实会话：demo 数据只兜底展示，不当用户数据继续用（§8.2）
  watch(offline, (v, prev) => { if (prev && !v && useMock.value) initSession() })

  // 离开页面时保存快照，回来恢复
  onBeforeUnmount(() => saveSnapshot())

  // 页面卸载：取消挂起请求（AbortError，不置离线标记）
  onUnmounted(() => scope.cancel())

  // 离线只读：真实会话（非 mock）在 offline 期间禁止开始考核/提交；mock 演示路径不受影响
  const canWrite = computed(() => canSubmit({ offline: offline.value, useMock: useMock.value, busy: busy.value }))

  // 开始考核：真实模式调 start_quiz + current；mock 模式仅切 UI
  async function startQuiz() {
    if (useMock.value) { quizzing.value = true; return }
    if (offline.value) { alert(OFFLINE_WRITE_TIP); return }
    busy.value = '面试官 AGENT 出题中…'
    try {
      await apiStartQuiz(sessionId.value)
      const cur = await getCurrent(sessionId.value)
      quiz.value = {
        question: cur.variant_stem,
        followTag: `考核 ${cur.progress} · 已打乱`,
        keywords: cur.keywords || [],
      }
      quizQid = cur.question_id
      answerText.value = ''
      fbShow.value = false
      quizzing.value = true
    } catch (e) {
      console.warn('[memorize] start_quiz 失败：', e.message)
      alert('开始考核失败：' + e.message)
    } finally {
      busy.value = ''
    }
  }

  // 提示（关键词）：反复点击开合
  function toggleKw() { kwShow.value = !kwShow.value }

  // 提交作答：真实模式拿即时评分反馈；答错后端自动入待补答队列
  async function submitQuiz() {
    if (useMock.value) { fbShow.value = true; return }
    if (offline.value) { alert(OFFLINE_WRITE_TIP); return }
    const text = answerText.value.trim()
    if (!text) return
    busy.value = '评分 AGENT 批改中…'
    try {
      if (!quizKey) quizKey = newIdempotencyKey()   // 一次提交一个键，失败重试复用
      const d = await submitAnswer(sessionId.value, text, undefined, quizKey)
      feedback.value = toFeedback(d.score, text, d.standard_answer)
      fbShow.value = true
      if (d.finished) {
        finished.value = true
        summary.value = d.summary
      } else {
        // 预存下一题（关键词从 create_session 的题目列表里取）
        const nx = d.next_question
        quiz.value = {
          question: nx.variant_stem,
          followTag: `考核 ${nx.progress} · 已打乱`,
          keywords: kwMap[nx.question_id] || [],
        }
        quizQid = nx.question_id
      }
      saveSnapshot()   // 即时落快照：崩溃/切页后按服务端状态恢复
    } catch (e) {
      console.warn('[memorize] answer 失败：', e.message)
      alert('提交失败：' + e.message)
    } finally {
      busy.value = ''
    }
  }

  // 下一题：清空作答与反馈，展示预存的下一题
  function nextQuestion() {
    fbShow.value = false
    kwShow.value = false
    answerText.value = ''
    quizKey = null   // 新题新幂等键
  }

  return {
    loadError, quizzing, kwShow, fbShow,
    topLeft, topRight, questions, quiz, answerText, feedback, finished, summary, busy, canWrite,
    startQuiz, submitQuiz, nextQuestion, toggleKw,
  }
}
