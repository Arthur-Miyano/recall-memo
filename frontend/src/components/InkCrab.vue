<script setup>
// 全局组件：水墨小螃蟹（智能助理入口）+ 对话面板
// 职责：常驻页面、原地挥钳待机；点击开合对话面板（5 个快捷提示词 + 自由输入 + 思考过程展示）；
//       可按住拖动到任意位置（位置存 localStorage），待机时偶尔吐泡泡，拖动结束 / 收到答复时吐一串
// 数据流：POST /api/assistant/chat（{message} 或 {quick}）→ {thinking, reply}，每次问答后端落库；
//         GET  /api/assistant/history —— 面板首次打开时拉取最近 50 条历史渲染（思考过程随消息展示）；
//         请求失败回退 mock/assistant.js 演示回复（console.warn，不打断对话、不白屏）
// 动效：
//   - 待机：crabSway 身体轻摇 + clawWave 双钳交替挥舞 + crabBlink 眨眼（纯 CSS）
//   - 拖动：pointerdown/move/up，位移 < 6px 视为点击（开合面板），否则为拖动；拖动中身体定格、双钳加速
//   - 吐泡泡：bubbles 数组渲染墨线圈，bubbleUp 上升消散；定时器每 4.5s 吐一个，burst() 连吐三个
//   - 面板开合：chat-panel.show 的 screenIn 动画，面板位置跟随螃蟹（下半屏则向上开）
//   - 面板缩放：CSS resize:both（手柄在面板右下角，与螃蟹拖动互不干扰），尺寸存 localStorage，
//     ResizeObserver 监听保存；panelStyle 按当前尺寸钳制在视口内
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { assistant } from '../mock/assistant'
import { assistantChat, getAssistantHistory } from '../api'

// 快捷按钮 → 后端 quick 指令
const QUICK_KEYS = {
  今日总结: 'today', 最近总结: 'recent', 全部总结: 'all',
  重点背诵建议: 'focus', 制定背诵计划: 'plan',
}

const panelShow = ref(false)
const inputText = ref('')
const logEl = ref(null)
const panelEl = ref(null)
// 聊天记录：{ who, text } 普通消息；{ who, think: [] } 思考过程
const messages = ref([{ who: '记忆助手', text: assistant.greeting }])

let historyLoaded = false  // 历史只拉一次，之后的问答直接本地追加

function togglePanel() { panelShow.value = !panelShow.value }
function closePanel() { panelShow.value = false }

// 面板首次打开：拉取历史对话渲染（用户消息 + 助手思考过程 + 回复），失败保持现状
watch(panelShow, async (show) => {
  if (!show || historyLoaded) return
  historyLoaded = true
  try {
    const d = await getAssistantHistory(50)
    for (const m of d.messages || []) {
      if (m.role === 'assistant' && Array.isArray(m.thinking) && m.thinking.length) {
        messages.value.push({ who: '思考过程', think: m.thinking })
      }
      messages.value.push({ who: m.role === 'user' ? '你' : '记忆助手', text: m.content })
    }
    scrollBottom()
  } catch (e) {
    console.warn('[crab] 拉取对话历史失败，保持当前会话：', e.message)
  }
})

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
// 面板尺寸：CSS resize:both 拖拽右下角手柄调整；ResizeObserver 保存到 localStorage，下次打开恢复
const panelSize = ref({ w: 380, h: 460 })
try {
  const saved = JSON.parse(localStorage.getItem('recall-chat-size'))
  if (saved && Number.isFinite(saved.w) && Number.isFinite(saved.h)) panelSize.value = saved
} catch { /* 损坏数据忽略，用默认尺寸 */ }

let resizeObserver = null

onMounted(() => {
  // 监听面板尺寸变化（resize 手柄拖动），写入 localStorage；面板隐藏时尺寸为 0，不保存
  resizeObserver = new ResizeObserver(entries => {
    const r = entries[0]?.contentRect
    if (!r || !panelShow.value || r.width < 10 || r.height < 10) return
    panelSize.value = { w: Math.round(r.width), h: Math.round(r.height) }
    localStorage.setItem('recall-chat-size', JSON.stringify(panelSize.value))
  })
  if (panelEl.value) resizeObserver.observe(panelEl.value)
})
onUnmounted(() => { resizeObserver?.disconnect() })

// 面板跟随螃蟹：水平对齐并钳制在视口内；螃蟹在下半屏时面板向上开，避免被裁掉
// 位置随 panelSize 一起钳制：调整后若超出视口则收回到可见范围
const panelStyle = computed(() => {
  const vw = window.innerWidth, vh = window.innerHeight
  const { w, h } = panelSize.value
  const left = Math.min(Math.max(pos.value.x, 8), Math.max(8, vw - w - 8))
  const openBelow = pos.value.y + 92 + h < vh
  const top = openBelow
    ? Math.min(pos.value.y + 92, Math.max(8, vh - h - 8))
    : Math.max(8, pos.value.y - h - 8)
  return { left: left + 'px', top: top + 'px', width: w + 'px', height: h + 'px' }
})

// 滚动到底部
async function scrollBottom() {
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
}

// 发送提问：插入用户消息 → 「思考中…」→ 真实接口返回 thinking 调用链 + reply
// 快捷按钮传 quick 指令，自由输入传 message；失败回退 mock 演示回复
async function ask(text, quick) {
  messages.value.push({ who: '你', text })
  const thinkingMsg = { who: '思考过程', think: ['思考中…'] }
  messages.value.push(thinkingMsg)
  scrollBottom()
  try {
    const d = await assistantChat(quick ? { quick } : { message: text })
    thinkingMsg.think = d.thinking
    messages.value.push({ who: '记忆助手', text: d.reply })
  } catch (e) {
    console.warn('[crab] 助理接口失败，回退 mock 演示回复：', e.message)
    thinkingMsg.think = [...assistant.thinking, `（接口异常：${e.message}，以下为演示回复）`]
    messages.value.push({ who: '记忆助手', text: assistant.reply })
  }
  scrollBottom()
  burst()
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

  <!-- 对话面板：位置跟随螃蟹；resize:both 可拖拽右下角调整宽高（尺寸记忆在 localStorage） -->
  <div class="chat-panel" :class="{ show: panelShow }" :style="panelStyle" ref="panelEl">
    <div class="chat-head"><b>记忆助手</b><span>RECALL ASSISTANT</span><span class="x" @click="closePanel">✕</span></div>
    <div class="chat-quick">
      <button v-for="p in assistant.quickPrompts" :key="p.label" @click="ask(p.q, QUICK_KEYS[p.label])">{{ p.label }}</button>
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
