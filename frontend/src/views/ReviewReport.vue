<script setup>
// 屏幕三：终局复盘报告
// 职责：纸张式复盘（单题对照/维度分/遗漏点、薄弱点分析、错题去向），纸张可拖拽
// 数据流（真实接口，失败回退 mock/review.js 并 console.warn）：
//   GET /api/sessions/{id}/review   —— 面试结束跳来时按 session_id 取报告
//   GET /api/sessions/latest-review —— 直接进入本页时取最近一次面试的报告
//   「错题去向」只做展示：答错/跳过的题已自动加入记忆训练的待补答队列
// 动效：
//   - 入场：纸张依次掉落（.screen.active .paper 的 drop 动画 + nth-child 延迟，纯 CSS）
//   - 拖拽：pointer 事件拖动 .paper-head，位移限制在桌面范围内（与原型边界一致）
import { reactive, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { reviewReport as rv } from '../mock/review'
import { getReview, getLatestReview } from '../api'

const route = useRoute()
const router = useRouter()

const desk = ref(null)
const fileNo = ref(rv.fileNo)
const title = ref(rv.title)
const meta = ref(rv.meta)
const papers = ref(rv.papers)
// 每张纸的拖拽偏移（null = 未拖过，回到文档流原位）
const poses = reactive(rv.papers.map(() => null))
const draggingIdx = ref(-1)

const STACK_LABEL = { python: 'PYTHON', agent: 'AGENT', vue3: 'VUE 3', mixed: '混合' }

function shortStem(s) {
  const t = (s || '').trim()
  return t.length <= 14 ? t : t.slice(0, 13) + '…'
}

// 真实报告 JSON → 纸张结构
function toPapers(report) {
  const out = report.per_question.map((q, i) => ({
    kind: 'question',
    no: `Q${i + 1} — ${STACK_LABEL[q.tech_stack] || String(q.tech_stack).toUpperCase()}${q.followup ? ` · 追问链 ${q.followup}` : ''}`,
    title: shortStem(q.stem),
    score: q.skipped ? '0.0' : (q.score ? String(q.score.total) : null),
    stamp: q.skipped ? '已跳过' : (q.score?.is_reciting ? '背诵痕迹' : null),
    dims: q.score ? [
      { label: '准确性 50%', value: Math.round(q.score.accuracy), seal: false },
      { label: '逻辑 30%', value: Math.round(q.score.logic), seal: false },
      { label: '自然度 20%', value: Math.round(q.score.naturalness), seal: q.score.is_reciting },
    ] : null,
    yourAnswer: q.skipped ? '（跳过未作答）' : q.user_answer,
    stdAnswer: q.standard_answer,
    misses: q.score?.missed_points?.length ? q.score.missed_points.map(p => `遗漏：${p}`) : null,
  }))
  const a = report.analysis || {}
  out.push({
    kind: 'analysis',
    no: 'ANALYSIS — 智能助理 AGENT',
    title: '薄弱点分析',
    weakPoints: [
      ...(a.weak_points || []),
      a.overall && `总评：${a.overall}`,
      a.misunderstandings && `理解偏差：${a.misunderstandings}`,
      a.reciting_notes && `背诵痕迹：${a.reciting_notes}`,
    ].filter(Boolean),
  })
  const stemOf = {}
  report.per_question.forEach(q => { stemOf[q.question_id] = q.stem })
  out.push({
    kind: 'followup',
    no: 'FOLLOW-UP — 后续安排',
    title: '答错题目去向',
    retryQuestions: (report.retry_list || []).map(qid => shortStem(stemOf[qid] || `题 #${qid}`)),
    note: '// 已自动加入「记忆训练」待补答队列，复习巩固在那里完成',
    cta: '去记忆训练 →',
  })
  return out
}

onMounted(async () => {
  try {
    const sid = route.query.session_id || null
    const report = sid ? await getReview(sid) : await getLatestReview()
    fileNo.value = `INTERVIEW REPORT — FILE №${new Date().toISOString().slice(0, 10).replaceAll('-', '')}-${String(report.session_id).padStart(2, '0')}`
    meta.value = [
      `场次：${STACK_LABEL[report.tech_stack] || report.tech_stack} ${report.question_count} 题 · 平均 ${report.avg_total ?? '—'} 分`,
      `${new Date().toLocaleDateString('zh-CN')} — 面试官 AGENT / 评分 AGENT 联署`,
    ]
    papers.value = toPapers(report)
    poses.splice(0, poses.length, ...papers.value.map(() => null))
  } catch (e) {
    console.warn('[review] 获取复盘报告失败，回退 mock 演示数据：', e.message)
  }
})

// 拖拽开始：记录指针相对纸张左上角的偏移，绑定 window 级 move/up
function onDragStart(e, i) {
  const p = e.currentTarget.closest('.paper')
  const r = p.getBoundingClientRect()
  const dx = e.clientX - r.left, dy = e.clientY - r.top
  draggingIdx.value = i
  if (!poses[i]) poses[i] = { left: 0, top: 0 }
  const move = ev => {
    const dr = desk.value.getBoundingClientRect()
    poses[i] = {
      left: Math.max(-40, Math.min(dr.width - 120, ev.clientX - dr.left - dx)) + 'px',
      top: Math.max(-10, Math.min(120, ev.clientY - dr.top - dy)) + 'px',
    }
  }
  const up = () => {
    draggingIdx.value = -1
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
  e.preventDefault()
}
// 像素条：分数 → 10 格（向下取整，与原型静态格数一致：95→9 格、90→9 格）
function cells(v) { return Math.floor(v / 10) }
</script>

<template>
  <section class="screen active">
    <div class="rv-head">
      <div>
        <div class="mono" style="font-size:11px;letter-spacing:.14em;color:var(--ink-45);margin-bottom:10px">{{ fileNo }}</div>
        <h1 class="rv-title">{{ title }}</h1>
      </div>
      <span class="spacer"></span>
      <div class="meta">{{ meta[0] }}<br>{{ meta[1] }}</div>
    </div>

    <div class="rv-desk" ref="desk">
      <div
        class="paper"
        v-for="(p, i) in papers"
        :key="p.no"
        :class="{ dragging: draggingIdx === i }"
        :style="poses[i] ? { position: 'relative', left: poses[i].left, top: poses[i].top } : {}"
      >
        <div class="paper-head" @pointerdown="onDragStart($event, i)">
          <span class="no">{{ p.no }}</span>
          <h3>{{ p.title }}</h3>
          <span class="score" v-if="p.score">{{ p.score }}<small> /100</small></span>
        </div>

        <!-- 单题复盘：背诵痕迹印章 + 维度分 + 对照栏 + 遗漏点 -->
        <template v-if="p.kind === 'question'">
          <span class="stamp" v-if="p.stamp">{{ p.stamp }}</span>
          <div class="dims" v-if="p.dims">
            <div class="dim" v-for="d in p.dims" :key="d.label">
              {{ d.label }}<b :style="d.seal ? 'color:var(--seal)' : ''">{{ d.value }}</b>
              <div class="pixbar">
                <i v-for="n in 10" :key="n" :class="{ off: n > cells(d.value) }"></i>
              </div>
            </div>
          </div>
          <div class="compare">
            <div><span class="lbl">你的回答</span>{{ p.yourAnswer }}</div>
            <div><span class="lbl">标准答案</span>{{ p.stdAnswer }}</div>
          </div>
          <ul class="miss" style="margin-top:14px" v-if="p.misses">
            <li v-for="mm in p.misses" :key="mm">{{ mm }}</li>
          </ul>
        </template>

        <!-- 薄弱点分析 -->
        <ul class="weak-list" v-else-if="p.kind === 'analysis'">
          <li v-for="w in p.weakPoints" :key="w">{{ w }}</li>
        </ul>

        <!-- 答错题目去向（已进待补答队列，只做展示） -->
        <div class="retry-box" v-else-if="p.kind === 'followup'">
          <span class="tag" v-for="q in p.retryQuestions" :key="q">{{ q }}</span>
          <span class="iv-note">{{ p.note }}</span>
          <button class="btn" @click="router.push('/memorize')">{{ p.cta }}</button>
        </div>
      </div>
    </div>
  </section>
</template>
