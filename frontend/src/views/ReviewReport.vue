<script setup>
// 屏幕三：终局复盘报告
// 职责：纸张式复盘（单题对照/维度分/遗漏点、薄弱点分析、错题去向），纸张可拖拽
// 数据流：mock/review.js → reviewReport（未来 GET /api/review/latest）
// 动效：
//   - 入场：纸张依次掉落（.screen.active .paper 的 drop 动画 + nth-child 延迟，纯 CSS）
//   - 拖拽：pointer 事件拖动 .paper-head，位移限制在桌面范围内（与原型边界一致）
import { reactive, ref } from 'vue'
import { reviewReport as rv } from '../mock/review'

const desk = ref(null)
// 每张纸的拖拽偏移（null = 未拖过，回到文档流原位）
const poses = reactive(rv.papers.map(() => null))
const draggingIdx = ref(-1)

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
        <div class="mono" style="font-size:11px;letter-spacing:.14em;color:var(--ink-45);margin-bottom:10px">{{ rv.fileNo }}</div>
        <h1 class="rv-title">{{ rv.title }}</h1>
      </div>
      <span class="spacer"></span>
      <div class="meta">{{ rv.meta[0] }}<br>{{ rv.meta[1] }}</div>
    </div>

    <div class="rv-desk" ref="desk">
      <div
        class="paper"
        v-for="(p, i) in rv.papers"
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
            <li v-for="m in p.misses" :key="m">{{ m }}</li>
          </ul>
        </template>

        <!-- 薄弱点分析 -->
        <ul class="weak-list" v-else-if="p.kind === 'analysis'">
          <li v-for="w in p.weakPoints" :key="w">{{ w }}</li>
        </ul>

        <!-- 答错题目去向 -->
        <div class="retry-box" v-else-if="p.kind === 'followup'">
          <span class="tag" v-for="q in p.retryQuestions" :key="q">{{ q }}</span>
          <span class="iv-note">{{ p.note }}</span>
          <button class="btn">{{ p.cta }}</button>
        </div>
      </div>
    </div>
  </section>
</template>
