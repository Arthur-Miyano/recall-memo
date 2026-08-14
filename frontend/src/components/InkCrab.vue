<script setup>
// 全局组件：水墨小螃蟹（智能助理入口）+ 对话面板
// 职责：常驻页面、原地挥钳待机；点击开合对话面板（5 个快捷提示词 + 自由输入 + 思考过程展示）；
//       可按住拖动到任意位置（位置存 localStorage），待机时偶尔吐泡泡，拖动结束 / 收到答复时吐一串
// 数据流：mock/assistant.js → assistant（未来 POST /api/assistant/chat）
// 动效：
//   - 待机：crabSway 身体轻摇 + clawWave 双钳交替挥舞 + crabBlink 眨眼（纯 CSS）
//   - 拖动：pointerdown/move/up，位移 < 6px 视为点击（开合面板），否则为拖动；拖动中身体定格、双钳加速
//   - 吐泡泡：bubbles 数组渲染墨线圈，bubbleUp 上升消散；定时器每 4.5s 吐一个，burst() 连吐三个
//   - 面板开合：chat-panel.show 的 screenIn 动画，面板位置跟随螃蟹（下半屏则向上开）
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { assistant } from '../mock/assistant'

const panelShow = ref(false)
const inputText = ref('')
const logEl = ref(null)
// 聊天记录：{ who, text } 普通消息；{ who, think: [] } 思考过程
const messages = ref([{ who: '记忆助手', text: assistant.greeting }])

function togglePanel() { panelShow.value = !panelShow.value }
function closePanel() { panelShow.value = false }

/* ---------- 拖动 ---------- */
// 螃蟹左上角坐标（fixed 定位），默认左上角；读取上次拖到的位置
const pos = ref({ x: 28, y: 76 })
try {
  const saved = JSON.parse(localStorage.getItem('recall-crab-pos'))
  if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) pos.value = saved
} catch { /* 损坏数据忽略，用默认位置 */ }

const dragging = ref(false)
let grabOffset = { x: 0, y: 0 }   // 按下点相对螃蟹左上角的偏移
let startClient = { x: 0, y: 0 }  // 按下时的指针坐标，用于计算位移区分点击/拖动
let dragDist = 0

function onPointerDown(e) {
  dragging.value = true
  dragDist = 0
  grabOffset = { x: e.clientX - pos.value.x, y: e.clientY - pos.value.y }
  startClient = { x: e.clientX, y: e.clientY }
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp, { once: true })
}

function onPointerMove(e) {
  dragDist = Math.hypot(e.clientX - startClient.x, e.clientY - startClient.y)
  // 跟随指针，钳制在视口内（螃蟹 84×84）
  pos.value = {
    x: Math.min(Math.max(e.clientX - grabOffset.x, 0), window.innerWidth - 84),
    y: Math.min(Math.max(e.clientY - grabOffset.y, 0), window.innerHeight - 84),
  }
}

function onPointerUp() {
  window.removeEventListener('pointermove', onPointerMove)
  dragging.value = false
  localStorage.setItem('recall-crab-pos', JSON.stringify(pos.value))
  if (dragDist < 6) togglePanel()  // 几乎没位移 = 点击
  else burst()                     // 拖动落地，吐一串泡泡
}

/* ---------- 吐泡泡 ---------- */
// bubbles：{ id, size, ox(嘴部水平位置), dx(上升时水平漂移), dur }，动画结束后移除
const bubbles = ref([])
let bubbleSeq = 0
let bubbleTimer = null

function spawnBubble(big) {
  const id = ++bubbleSeq
  bubbles.value.push({
    id,
    size: big ? 6 + Math.random() * 8 : 3 + Math.random() * 5,
    ox: 32 + Math.random() * 20,
    dx: (Math.random() * 28 - 14).toFixed(0) + 'px',
    dur: (1.8 + Math.random() * 1.2).toFixed(2) + 's',
  })
  setTimeout(() => { bubbles.value = bubbles.value.filter(b => b.id !== id) }, 3200)
}

// 连吐三个大泡泡（拖动落地、收到答复时调用）
function burst() { for (let i = 0; i < 3; i++) setTimeout(() => spawnBubble(true), i * 160) }

onMounted(() => { bubbleTimer = setInterval(() => spawnBubble(false), 4500) })
onUnmounted(() => {
  clearInterval(bubbleTimer)
  window.removeEventListener('pointermove', onPointerMove)
})

/* ---------- 对话面板 ---------- */
// 面板跟随螃蟹：水平对齐并钳制在视口内；螃蟹在下半屏时面板向上开，避免被裁掉
const panelStyle = computed(() => {
  const vw = window.innerWidth, vh = window.innerHeight
  const left = Math.min(Math.max(pos.value.x, 8), vw - 396)
  const openBelow = pos.value.y + 92 + 430 < vh
  const top = openBelow ? pos.value.y + 92 : Math.max(8, pos.value.y - 438)
  return { left: left + 'px', top: top + 'px' }
})

// 滚动到底部
async function scrollBottom() {
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
}

// 发送提问：插入用户消息 → 思考过程 → 延迟后插入答复（演示用假回复），答复时吐泡泡
function ask(text) {
  messages.value.push({ who: '你', text })
  messages.value.push({ who: '思考过程', think: assistant.thinking })
  scrollBottom()
  setTimeout(() => {
    messages.value.push({ who: '记忆助手', text: assistant.reply })
    scrollBottom()
    burst()
  }, assistant.replyDelayMs)
}

// 发送自由输入（按钮 / 回车）
function send() {
  const t = inputText.value.trim()
  if (t) { ask(t); inputText.value = '' }
}
</script>

<template>
  <!-- 水墨小螃蟹：笔触式 path，躯干+双钳+八足，纯墨色；可拖动，位置记忆在 localStorage -->
  <div
    class="crab"
    :class="{ dragging }"
    :style="{ left: pos.x + 'px', top: pos.y + 'px' }"
    title="记忆助手"
    @pointerdown="onPointerDown"
  >
    <!-- 泡泡层：嘴部（双眼之间上方）升起，墨线圈 -->
    <span
      v-for="b in bubbles"
      :key="b.id"
      class="crab-bubble"
      :style="{ left: b.ox + 'px', top: '20px', width: b.size + 'px', height: b.size + 'px', '--dx': b.dx, '--dur': b.dur }"
    ></span>
    <svg viewBox="0 0 84 84" fill="none" stroke="var(--ink)" stroke-linecap="round">
      <g class="crab-body">
        <!-- 躯干：两笔浓淡叠加出水墨感 -->
        <ellipse cx="42" cy="48" rx="16" ry="11" fill="var(--ink)" opacity=".88"/>
        <ellipse cx="42" cy="46" rx="13" ry="8.5" fill="var(--ink-45)" opacity=".5" stroke="none"/>
        <!-- 眼 -->
        <line x1="37" y1="38" x2="36" y2="33" stroke-width="2.2"/>
        <line x1="47" y1="38" x2="48" y2="33" stroke-width="2.2"/>
        <circle class="eye" cx="36" cy="32" r="1.8" fill="var(--ink)" stroke="none"/>
        <circle class="eye" cx="48" cy="32" r="1.8" fill="var(--ink)" stroke="none"/>
        <!-- 左足（四笔） -->
        <path d="M28 44 Q20 42 15 36" stroke-width="2.4"/>
        <path d="M27 49 Q18 50 12 47" stroke-width="2.4"/>
        <path d="M28 54 Q20 58 14 58" stroke-width="2.4"/>
        <path d="M31 58 Q26 64 20 66" stroke-width="2.4"/>
        <!-- 右足 -->
        <path d="M56 44 Q64 42 69 36" stroke-width="2.4"/>
        <path d="M57 49 Q66 50 72 47" stroke-width="2.4"/>
        <path d="M56 54 Q64 58 70 58" stroke-width="2.4"/>
        <path d="M53 58 Q58 64 64 66" stroke-width="2.4"/>
        <!-- 左钳 -->
        <g class="claw-l">
          <path d="M27 42 Q18 34 16 26" stroke-width="2.8"/>
          <path d="M16 26 Q13 20 17 17 Q22 15 23 21 Q24 26 19 28 Z" fill="var(--ink)" stroke-width="1.5"/>
        </g>
        <!-- 右钳 -->
        <g class="claw-r">
          <path d="M57 42 Q66 34 68 26" stroke-width="2.8"/>
          <path d="M68 26 Q71 20 67 17 Q62 15 61 21 Q60 26 65 28 Z" fill="var(--ink)" stroke-width="1.5"/>
        </g>
      </g>
    </svg>
    <span class="crab-tip">记忆助手 · 点击召唤 · 按住拖我</span>
  </div>

  <!-- 对话面板：位置跟随螃蟹 -->
  <div class="chat-panel" :class="{ show: panelShow }" :style="panelStyle">
    <div class="chat-head"><b>记忆助手</b><span>RECALL ASSISTANT</span><span class="x" @click="closePanel">✕</span></div>
    <div class="chat-quick">
      <button v-for="p in assistant.quickPrompts" :key="p.label" @click="ask(p.q)">{{ p.label }}</button>
    </div>
    <div class="chat-log" ref="logEl">
      <div class="chat-msg" v-for="(m, i) in messages" :key="i">
        <span class="who">{{ m.who }}</span>
        <div class="chat-think" v-if="m.think">
          <div v-for="(t, ti) in m.think" :key="ti">{{ t }}</div>
        </div>
        <template v-else>{{ m.text }}</template>
      </div>
    </div>
    <div class="chat-input">
      <input v-model="inputText" placeholder="问点什么…" @keydown.enter="send">
      <button @click="send">发送</button>
    </div>
  </div>
</template>
