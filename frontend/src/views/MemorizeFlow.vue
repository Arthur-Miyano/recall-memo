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
//   - 标准答案区域选中句子后右键 → NoteSaver 浮动菜单，存进笔记（> 引用块追加，见 api/notes）
// 结构：会话恢复与题目推进（快照/恢复决策/幂等重放/考核推进）在 composables/useMemorizeSession.js
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { memorizeSession as m } from '../mock/memorize'
import { exportRecallCard } from '../utils/recallCard'
import { useMemorizeSession } from '../composables/useMemorizeSession'
import NoteSaver from '../components/NoteSaver.vue'

const router = useRouter()

// 会话态与推进逻辑全部由 composable 产出；本文件只留展示态
const {
  loadError, quizzing, kwShow, fbShow,
  topLeft, topRight, questions, quiz, answerText, feedback, finished, summary, busy,
  startQuiz, submitQuiz, nextQuestion, toggleKw,
} = useMemorizeSession()

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
onUnmounted(() => {
  window.removeEventListener('keydown', onZoomKey)
  document.body.style.overflow = ''   // 弹窗开着时跳路由也要解锁背景滚动
})
// 放大时锁定背景滚动
watch(zoomIdx, v => { document.body.style.overflow = v === null ? '' : 'hidden' })

// 像素条：分数 → 10 格（向下取整，与原型静态格数一致）
function cells(v) { return Math.floor(v / 10) }

/* ---------- 划句右键存笔记（标准答案区域） ---------- */
const noteSaver = ref(null)
function onNoteSelect(e, src) {
  const sel = window.getSelection()?.toString().trim()
  if (!sel) return   // 没选中文字：不拦截，走浏览器默认菜单
  e.preventDefault()
  noteSaver.value?.open(e.clientX, e.clientY, sel, src)
}

/* ---------- 答题框：随内容自动撑高（清空时复位） ---------- */
const answerEl = ref(null)
function fitAnswer() {
  const el = answerEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.max(260, el.scrollHeight) + 'px'
}
watch(answerText, v => { if (!v && answerEl.value) answerEl.value.style.height = '' })

/* ---------- 导出背诵卡片（总结页）：Canvas 手绘 PNG，见 utils/recallCard.js ---------- */
const cardBusy = ref(false)
async function exportCard() {
  if (cardBusy.value) return
  cardBusy.value = true
  try {
    await exportRecallCard({
      date: new Date(),
      count: summary.value?.question_count ?? questions.value.length,
      questions: questions.value.map(q => ({ title: q.title, answer: q.answer, retry: q.retry })),
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
        <!-- 创建会话失败的业务错误（空题库/LLM 不可用）：明确提示 + 出口 -->
        <div v-if="loadError" class="paper mem-q">
          <div class="paper-head">
            <span class="no">ERROR</span>
            <h3>无法开始训练</h3>
          </div>
          <p class="comment">{{ loadError }}</p>
          <div class="mem-actions">
            <button class="btn btn--ghost" @click="router.push('/bank')">去题库看看 →</button>
            <button class="btn" @click="router.push('/')">返回首页 →</button>
          </div>
        </div>
        <template v-else>
        <div class="paper mem-q mem-click" v-for="(q, i) in questions" :key="q.no" @click="openZoom(i)">
          <div class="paper-head">
            <span class="no">{{ q.no }}</span>
            <h3>{{ q.title }}</h3>
            <span class="retry-flag" v-if="q.retry">待补答</span>
          </div>
          <div class="answer" @contextmenu="onNoteSelect($event, q.title)"><span class="lbl">标准答案</span>{{ q.answer }}</div>
        </div>
        <div class="mem-actions">
          <button class="btn" :disabled="!!busy" @click="startQuiz">我记好了，开始考核 →</button>
          <span class="iv-note">// 考核时将打乱顺序，只显示变体题干；点击题目卡片可放大逐题观看</span>
        </div>
        </template>
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
        <textarea ref="answerEl" class="iv-input" :placeholder="m.quiz.placeholder" v-model="answerText" :disabled="fbShow" @input="fitAnswer"></textarea>
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
          <p class="iv-note" style="margin:6px 0 0">
            // AI 评分仅供训练参考 · 准确性50% 逻辑30% 自然度20%<template v-if="feedback.provider"> · {{ feedback.provider }}<template v-if="feedback.model">/{{ feedback.model }}</template></template>
          </p>
          <div class="compare">
            <div><span class="lbl">你的回答</span>{{ feedback.yourAnswer }}</div>
            <div @contextmenu="onNoteSelect($event, quiz.question)"><span class="lbl">标准答案</span>{{ feedback.stdAnswer }}</div>
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

    <!-- 划句右键存笔记：浮动菜单（标准答案区域选中文字后右键触发） -->
    <NoteSaver ref="noteSaver" />

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
          <div class="pm-answer" @contextmenu="onNoteSelect($event, questions[zoomIdx].title)"><span class="lbl">标准答案</span>{{ questions[zoomIdx].answer }}</div>
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
