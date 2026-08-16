<script setup>
// 屏幕：记忆训练流程（展示 → 考核 → 提示 → 即时反馈）
// 职责：阶段一展示题干+标准答案供记忆；阶段二打乱考核 + 评分 AGENT 即时反馈
// 数据流（真实接口，失败回退 mock/memorize.js 并 console.warn）：
//   POST /api/sessions {mode: memorize|review}   —— 抽题（待补答队列优先），返回题干+答案
//   POST /api/sessions/{id}/start_quiz           —— 打乱顺序，生成第一题变体题干
//   GET  /api/sessions/{id}/current              —— 当前题变体题干 + 关键词提示
//   POST /api/sessions/{id}/answer               —— 即时评分反馈；答错自动进待补答队列
// 动效：
//   - 纸张掉落入场：.screen.active .paper 的 drop 动画（纯 CSS）
//   - mem-stage.quizzing 切换展示/考核两个区域（CSS 显隐 + screenIn）
//   - 关键词提示 kw-hint.show、反馈面板 quiz-feedback.show（drop 动画）
//   - 展示阶段题目卡片点击 → .paper-modal 单题放大（宋体大题干 + 完整答案 + 上/下题导航，Esc/遮罩关闭）
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { memorizeSession as m } from '../mock/memorize'
import { createSession, startQuiz as apiStartQuiz, getCurrent, submitAnswer } from '../api'
import { exportRecallCard } from '../utils/recallCard'

const route = useRoute()
const router = useRouter()

// ---- mock 兜底态（后端不可用时展示演示数据） ----
const useMock = ref(false)
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
    yourAnswer,
    stdAnswer,
  }
}

onMounted(async () => {
  const mode = route.query.mode === 'review' ? 'review' : 'memorize'
  const count = Number(route.query.count) || 3
  const stack = typeof route.query.stack === 'string' ? route.query.stack : null
  try {
    const d = await createSession(mode, stack, count)
    sessionId.value = d.session_id
    topLeft.value = `${mode === 'review' ? 'RECALL' : 'MEMORIZE'} — ${(d.questions[0]?.tech_stack || stack || 'mixed').toUpperCase()} · 本轮 ${d.questions.length} 题`
    topRight.value = `${d.state} — ${mode === 'review' ? '回忆中' : '记忆中'}`
    questions.value = d.questions.map((q, i) => {
      kwMap[q.question_id] = q.keywords || []
      return { no: `题 ${i + 1} / ${d.questions.length}`, title: q.stem, retry: q.retry, answer: q.answer }
    })
  } catch (e) {
    console.warn('[memorize] 创建会话失败，回退 mock 演示数据：', e.message)
    useMock.value = true
  }
})

// 开始考核：真实模式调 start_quiz + current；mock 模式仅切 UI
async function startQuiz() {
  if (useMock.value) { quizzing.value = true; return }
  busy.value = '面试官 AGENT 出题中…'
  try {
    await apiStartQuiz(sessionId.value)
    const cur = await getCurrent(sessionId.value)
    quiz.value = {
      question: cur.variant_stem,
      followTag: `考核 ${cur.progress} · 已打乱`,
      keywords: cur.keywords || [],
    }
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
  const text = answerText.value.trim()
  if (!text) return
  busy.value = '评分 AGENT 批改中…'
  try {
    const d = await submitAnswer(sessionId.value, text)
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
    }
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
}

/* ---------- 单题放大（展示阶段） ---------- */
// 点击题目卡片放大：zoomIdx 为 questions 下标（null=关闭）；←/→ 键也可翻题
const zoomIdx = ref(null)

function openZoom(i) { zoomIdx.value = i }
function closeZoom() { zoomIdx.value = null }
function zoomPrev() { if (zoomIdx.value > 0) zoomIdx.value-- }
function zoomNext() { if (zoomIdx.value < questions.value.length - 1) zoomIdx.value++ }

function onZoomKey(e) {
  if (zoomIdx.value === null) return
  if (e.key === 'Escape') closeZoom()
  else if (e.key === 'ArrowLeft') zoomPrev()
  else if (e.key === 'ArrowRight') zoomNext()
}
onMounted(() => window.addEventListener('keydown', onZoomKey))
onUnmounted(() => window.removeEventListener('keydown', onZoomKey))
// 放大时锁定背景滚动
watch(zoomIdx, v => { document.body.style.overflow = v === null ? '' : 'hidden' })

// 像素条：分数 → 10 格（向下取整，与原型静态格数一致）
function cells(v) { return Math.floor(v / 10) }

/* ---------- 导出背诵卡片（总结页）：Canvas 手绘 PNG，见 utils/recallCard.js ---------- */
const cardBusy = ref(false)
async function exportCard() {
  if (cardBusy.value) return
  cardBusy.value = true
  try {
    await exportRecallCard({
      date: new Date(),
      count: summary.value?.question_count ?? questions.value.length,
      questions: questions.value.map(q => ({ title: q.title, retry: q.retry })),
    })
  } catch (e) {
    console.warn('[memorize] 导出背诵卡片失败：', e.message)
    alert('导出失败：' + e.message)
  } finally {
    cardBusy.value = false
  }
}
</script>

<template>
  <section class="screen active">
    <div class="mem-stage" id="mem-stage" :class="{ quizzing }">
      <div class="iv-topbar">
        <span>{{ topLeft }}</span>
        <span class="spacer"></span>
        <span>{{ busy || topRight }}</span>
      </div>
      <div class="iv-line" style="margin-bottom:36px"><i style="width:100%"></i></div>

      <!-- 阶段一：展示题干+答案供记忆（点击卡片单题放大） -->
      <div class="mem-show">
        <div class="paper mem-q mem-click" v-for="(q, i) in questions" :key="q.no" @click="openZoom(i)">
          <div class="paper-head">
            <span class="no">{{ q.no }}</span>
            <h3>{{ q.title }}</h3>
            <span class="retry-flag" v-if="q.retry">待补答</span>
          </div>
          <div class="answer"><span class="lbl">标准答案</span>{{ q.answer }}</div>
        </div>
        <div class="mem-actions">
          <button class="btn" :disabled="!!busy" @click="startQuiz">我记好了，开始考核 →</button>
          <span class="iv-note">// 考核时将打乱顺序，只显示变体题干；点击题目卡片可放大逐题观看</span>
        </div>
      </div>

      <!-- 阶段二：打乱考核 + 即时反馈 -->
      <div class="quiz-zone">
        <div class="iv-agent">面试官 AGENT 提问中</div>
        <h2 class="iv-question" style="font-size:clamp(22px,2.6vw,30px)">{{ quiz.question }}</h2>
        <div class="iv-follow"><span class="tag">{{ quiz.followTag }}</span></div>
        <div style="margin-bottom:16px">
          <button class="btn btn--ghost" style="padding:7px 20px;font-size:12px" @click="toggleKw">提示（关键词）</button>
          <div class="kw-hint" :class="{ show: kwShow }">
            <span class="tag" v-for="k in quiz.keywords" :key="k">{{ k }}</span>{{ ' ' }}
          </div>
        </div>
        <textarea class="iv-input" style="min-height:150px" :placeholder="m.quiz.placeholder" v-model="answerText" :disabled="fbShow"></textarea>
        <div class="iv-actions">
          <button class="btn" :disabled="!!busy || fbShow" @click="submitQuiz">{{ busy || '提交回答' }}</button>
        </div>

        <!-- 即时反馈面板 -->
        <div class="paper quiz-feedback" :class="{ show: fbShow }">
          <div class="paper-head">
            <span class="no">{{ feedback.no }}</span>
            <h3>{{ finished ? '本轮最后一题 · 反馈' : feedback.title }}</h3>
            <span class="score">{{ feedback.score }}<small> /100</small></span>
          </div>
          <div class="dims">
            <div class="dim" v-for="d in feedback.dims" :key="d.label">
              {{ d.label }}<b :style="d.seal ? 'color:var(--seal)' : ''">{{ d.value }}</b>
              <div class="pixbar">
                <i v-for="i in 10" :key="i" :class="{ off: i > cells(d.value) }"></i>
              </div>
            </div>
          </div>
          <p class="comment">{{ feedback.comment }}</p>
          <div class="compare">
            <div><span class="lbl">你的回答</span>{{ feedback.yourAnswer }}</div>
            <div><span class="lbl">标准答案</span>{{ feedback.stdAnswer }}</div>
          </div>
          <!-- 本轮总结（全部答完后） -->
          <div v-if="finished && summary" style="margin-top:14px">
            <p class="comment">
              本轮 {{ summary.question_count }} 题 · 平均 {{ summary.avg_total ?? '—' }} 分
              <template v-if="summary.reciting_count"> · 背诵痕迹 {{ summary.reciting_count }} 题</template>
            </p>
            <ul class="miss">
              <li v-for="p in summary.per_question" :key="p.question_id">题 #{{ p.question_id }}：{{ p.total }} 分</li>
            </ul>
          </div>
          <div class="mem-actions">
            <button class="btn" v-if="!finished" @click="nextQuestion">下一题 →</button>
            <template v-else>
              <button class="btn btn--ghost" :disabled="cardBusy" @click="exportCard">{{ cardBusy ? '绘制中…' : '导出背诵卡片 ↓' }}</button>
              <button class="btn" @click="router.push('/')">完成，返回首页 →</button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 单题放大 modal：宋体大题干 + 完整标准答案 + 上/下题导航（Esc / 点遮罩关闭，←/→ 翻题） -->
    <div class="pm-overlay" v-if="zoomIdx !== null && questions[zoomIdx]" @click.self="closeZoom">
      <div class="pm-paper" role="dialog" aria-label="题目放大查看">
        <div class="pm-head">
          <span class="fig">{{ questions[zoomIdx].no }}<template v-if="questions[zoomIdx].retry"> · 待补答</template></span>
          <h2>题目记忆</h2>
          <button class="pm-close" title="关闭（Esc）" @click="closeZoom">✕</button>
        </div>
        <div class="pm-body">
          <div class="pm-q">{{ questions[zoomIdx].title }}</div>
          <div class="pm-answer"><span class="lbl">标准答案</span>{{ questions[zoomIdx].answer }}</div>
        </div>
        <div class="pm-nav">
          <button :disabled="zoomIdx === 0" @click="zoomPrev">← 上一题</button>
          <span class="idx">{{ zoomIdx + 1 }} / {{ questions.length }}</span>
          <button :disabled="zoomIdx === questions.length - 1" @click="zoomNext">下一题 →</button>
        </div>
      </div>
    </div>
  </section>
</template>
