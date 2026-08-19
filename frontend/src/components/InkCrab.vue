<script setup>
// 全局组件：水墨小螃蟹（智能助理入口）+ 对话面板
// 职责：常驻页面、原地挥钳待机；点击开合对话面板（5 个快捷提示词 + 自由输入 + 思考过程展示）；
//       可按住拖动到任意位置（位置存 localStorage），待机时偶尔吐泡泡，拖动结束 / 收到答复时吐一串
// 数据流：POST /api/assistant/chat（{message|quick, session_id?}）→ {thinking, reply, action, session_id}，每次问答后端落库；
//         action 为 LLM 提议的题库写操作（删/改/迁移），后端不执行——渲染确认卡片，
//         用户点「确认执行」后由本组件直接调题库接口（DELETE 逐个 / PATCH / POST migrate），结果追加为新消息；
//         GET  /api/assistant/sessions + POST /sessions + DELETE /sessions/{id} —— 多会话管理（头部「≡ 对话」抽屉）；
//         GET  /api/assistant/history?session_id= —— 切换会话 / 首次打开时拉取该会话最近 50 条渲染；
//         当前会话 id 存 localStorage（recall-chat-session），重开面板恢复；
//         请求失败回退 mock/assistant.js 演示回复（console.warn，不打断对话、不白屏）
// 动效：
//   - 待机：crabSway 身体轻摇 + clawWave 双钳交替挥舞 + crabBlink 眨眼（纯 CSS）
//   - 拖动：pointerdown/move/up，位移 < 6px 视为点击（开合面板），否则为拖动；拖动中身体定格、双钳加速
//   - 吐泡泡：bubbles 数组渲染墨线圈，bubbleUp 上升消散；定时器每 4.5s 吐一个，burst() 连吐三个
//   - 面板开合：chat-panel.show 的 screenIn 动画，面板位置跟随螃蟹（下半屏则向上开）
//   - 面板缩放：右下角自定义手柄（pointer capture 拖动），尺寸存 localStorage 下次打开恢复；
//     panelSize 是唯一尺寸数据源（拖哪写哪，不经 ResizeObserver，无反馈环）
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { assistant } from '../mock/assistant'
import {
  assistantChat, getAssistantHistory,
  getAssistantSessions, createAssistantSession, deleteAssistantSession,
  request, offline,
} from '../api'

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

let sessionsInited = false  // 会话列表只初始化一次；切换会话时单独拉历史

function togglePanel() { panelShow.value = !panelShow.value }
function closePanel() { panelShow.value = false; sessionsOpen.value = false }

/* ---------- 多会话管理 ---------- */
const sessions = ref([])             // 会话列表（updated_at 倒序）
const sessionsOpen = ref(false)      // 「≡ 对话」抽屉是否展开
const currentSessionId = ref(null)   // 当前会话 id（localStorage 记忆）

try {
  const saved = Number(localStorage.getItem('recall-chat-session'))
  if (Number.isInteger(saved) && saved > 0) currentSessionId.value = saved
} catch { /* 损坏数据忽略 */ }

// 拉取会话列表；接口失败不白屏，保持现状
async function refreshSessions() {
  try {
    const d = await getAssistantSessions()
    sessions.value = d.sessions || []
  } catch (e) {
    console.warn('[crab] 拉取会话列表失败：', e.message)
  }
}

// 拉取指定会话历史并渲染（清空当前消息，保留开场白在最前）
async function loadHistory(sessionId) {
  try {
    const d = await getAssistantHistory(50, sessionId)
    const hist = []
    for (const m of d.messages || []) {
      if (m.role === 'assistant' && Array.isArray(m.thinking) && m.thinking.length) {
        hist.push({ who: '思考过程', think: m.thinking })
      }
      hist.push({ who: m.role === 'user' ? '你' : '记忆助手', text: m.content })
    }
    messages.value = [{ who: '记忆助手', text: assistant.greeting }, ...hist]
    scrollBottom()
  } catch (e) {
    console.warn('[crab] 拉取对话历史失败，保持当前会话：', e.message)
  }
}

// 切换当前会话：记忆 id、拉历史、收起抽屉
async function switchSession(id) {
  if (id === currentSessionId.value) { sessionsOpen.value = false; return }
  currentSessionId.value = id
  localStorage.setItem('recall-chat-session', String(id))
  sessionsOpen.value = false
  messages.value = [{ who: '记忆助手', text: assistant.greeting }]
  await loadHistory(id)
}

// 新建空会话并切换过去
async function newSession() {
  try {
    const s = await createAssistantSession()
    sessions.value = [s, ...sessions.value]
    await switchSession(s.id)
  } catch (e) {
    console.warn('[crab] 新建会话失败：', e.message)
  }
}

// 删除会话：单击即删；删的是当前会话则切到最新剩余会话，没有则新建
async function removeSession(s) {
  try {
    await deleteAssistantSession(s.id)
  } catch (e) {
    console.warn('[crab] 删除会话失败：', e.message)
    return
  }
  sessions.value = sessions.value.filter(x => x.id !== s.id)
  if (s.id === currentSessionId.value) {
    if (sessions.value.length) await switchSession(sessions.value[0].id)
    else { currentSessionId.value = null; await newSession() }
  }
}

// 面板首次打开：初始化会话列表 → 恢复/选定当前会话 → 拉历史；失败回退旧行为（全量历史）
watch(panelShow, async (show) => {
  if (!show || sessionsInited) return
  sessionsInited = true
  await refreshSessions()
  if (!sessions.value.length) {
    // 后端无会话（或接口失败）：试建一个；建不了则按旧行为拉全量历史
    try {
      const s = await createAssistantSession()
      sessions.value = [s]
      currentSessionId.value = s.id
      localStorage.setItem('recall-chat-session', String(s.id))
      return  // 新会话无历史，开场白即可
    } catch (e) {
      console.warn('[crab] 会话接口不可用，回退全量历史模式：', e.message)
      await loadHistory(null)
      return
    }
  }
  const saved = sessions.value.find(s => s.id === currentSessionId.value)
  currentSessionId.value = (saved || sessions.value[0]).id
  localStorage.setItem('recall-chat-session', String(currentSessionId.value))
  await loadHistory(currentSessionId.value)
})

// 「≡ 对话」按钮：开合抽屉，展开时顺便刷新列表（updated_at 可能因新问答变化）
function toggleSessions() {
  sessionsOpen.value = !sessionsOpen.value
  if (sessionsOpen.value) refreshSessions()
}

// 会话时间标注：MM-DD HH:mm（mono 小字）
function fmtTime(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const p = n => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

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
// 面板尺寸：右下角自定义手柄拖动调整（pointer capture，与螃蟹拖动互不干扰）；
// 尺寸存 localStorage，下次打开恢复。panelSize 是唯一数据源：
// 手柄拖动直接写 panelSize，不经 ResizeObserver——原生 resize 手柄太小难抓，
// 且 content-box/border-box 口径差曾导致"松手慢慢缩回"的反馈环
const panelSize = ref({ w: 380, h: 460 })
try {
  const saved = JSON.parse(localStorage.getItem('recall-chat-size'))
  if (saved && Number.isFinite(saved.w) && Number.isFinite(saved.h)) panelSize.value = saved
} catch { /* 损坏数据忽略，用默认尺寸 */ }

// 手柄拖动：pointerdown 记起点尺寸，move 钳制范围写入，up 持久化
const PANEL_MIN = { w: 320, h: 360 }
let gripDrag = null   // { x, y, w, h } 拖动起点
function onGripDown(e) {
  e.preventDefault()
  e.target.setPointerCapture(e.pointerId)   // 捕获后续 move/up，拖出手柄也不丢
  gripDrag = { x: e.clientX, y: e.clientY, w: panelSize.value.w, h: panelSize.value.h }
}
function onGripMove(e) {
  if (!gripDrag) return
  const maxW = Math.round(window.innerWidth * 0.9)
  const maxH = Math.round(window.innerHeight * 0.85)
  panelSize.value = {
    w: Math.min(Math.max(gripDrag.w + e.clientX - gripDrag.x, PANEL_MIN.w), maxW),
    h: Math.min(Math.max(gripDrag.h + e.clientY - gripDrag.y, PANEL_MIN.h), maxH),
  }
}
function onGripUp() {
  if (!gripDrag) return
  gripDrag = null
  localStorage.setItem('recall-chat-size', JSON.stringify(panelSize.value))
}

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
// 快捷按钮传 quick 指令，自由输入传 message；带上当前会话 id 落库；失败回退 mock 演示回复
async function ask(text, quick) {
  messages.value.push({ who: '你', text })
  const thinkingMsg = { who: '思考过程', think: ['思考中…'] }
  messages.value.push(thinkingMsg)
  scrollBottom()
  try {
    const payload = quick ? { quick } : { message: text }
    if (currentSessionId.value) payload.session_id = currentSessionId.value
    const d = await assistantChat(payload)
    // 未指定会话时后端会落到最近/自动新建的会话：以返回的 session_id 为准记下来
    if (d.session_id && d.session_id !== currentSessionId.value) {
      currentSessionId.value = d.session_id
      localStorage.setItem('recall-chat-session', String(d.session_id))
    }
    thinkingMsg.think = d.thinking
    // 助手消息可携带动作提议（后端只校验不执行）：随消息渲染确认卡片
    const msg = { who: '记忆助手', text: d.reply }
    if (d.action && typeof d.action === 'object') {
      msg.action = d.action
      msg.actionState = 'pending' // pending → done / cancelled；执行失败保持 pending 可重试
    }
    messages.value.push(msg)
  } catch (e) {
    console.warn('[crab] 助理接口失败，回退 mock 演示回复：', e.message)
    offline.value = true // 展示了演示回复，置全局离线角标（下一次任意请求成功后自动清除）
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

/* ---------- 动作卡片：确认后执行题库写操作 ---------- */
// 后端只提议不执行；确认后由这里直接调题库接口（DELETE 逐个 / PATCH / migrate）
async function runAction(m) {
  if (m.actionState !== 'pending' || m.actionRunning) return
  const a = m.action
  m.actionRunning = true
  try {
    let result = ''
    if (a.type === 'delete_questions') {
      let deleted = 0
      for (const id of a.question_ids) {
        try { await request(`/api/bank/questions/${id}`, { method: 'DELETE' }); deleted++ }
        catch (e) { console.warn(`[crab] 删除题目 #${id} 失败：`, e.message) }
      }
      result = `已删除 ${deleted} 道题`
        + (deleted < a.question_ids.length ? `（${a.question_ids.length - deleted} 道删除失败）` : '')
    } else if (a.type === 'edit_question') {
      await request(`/api/bank/questions/${a.question_ids[0]}`, { method: 'PATCH', body: a.changes })
      result = `已更新题目 #${a.question_ids[0]}（${Object.keys(a.changes).join('、')}）`
    } else if (a.type === 'migrate_questions') {
      const d = await request('/api/bank/questions/migrate', {
        method: 'POST', body: { question_ids: a.question_ids, to_stack: a.to_stack },
      })
      result = `已把 ${d.moved} 道题迁移到「${d.to_stack}」`
        + (d.missing && d.missing.length ? `（${d.missing.length} 道不存在被跳过）` : '')
    } else {
      throw new Error(`未知动作类型：${a.type}`)
    }
    m.actionState = 'done'
    messages.value.push({ who: '记忆助手', text: `${result}。题库已更新，到「题库」页可看到最新状态。` })
  } catch (e) {
    console.warn('[crab] 动作执行失败：', e.message)
    // 保持 pending 允许重试
    messages.value.push({ who: '记忆助手', text: `执行失败：${e.message}。可以点卡片上的「确认执行」重试，或取消。` })
  } finally {
    m.actionRunning = false
    scrollBottom()
  }
}

function cancelAction(m) {
  if (m.actionState !== 'pending' || m.actionRunning) return
  m.actionState = 'cancelled'
}

// 卡片头部的动作类型标注
const ACTION_LABELS = { delete_questions: '删除题目', edit_question: '修改题目', migrate_questions: '迁移题目' }
function actionLabel(a) { return ACTION_LABELS[a.type] || '题库操作' }
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

  <!-- 对话面板：位置跟随螃蟹；右下角自定义手柄拖动调宽高（尺寸记忆在 localStorage） -->
  <div class="chat-panel" :class="{ show: panelShow }" :style="panelStyle" ref="panelEl">
    <div class="chat-head">
      <button class="sess-btn" title="对话列表" @click="toggleSessions">≡ 对话</button>
      <b>记忆助手</b><span>RECALL ASSISTANT</span><span class="x" @click="closePanel">✕</span>
    </div>
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
        <!-- 动作卡片：助手提议的题库写操作，确认后才执行 -->
        <div class="action-card" v-if="m.action">
          <div class="ac-head">{{ actionLabel(m.action) }} · {{ m.action.question_ids.length }} 题</div>
          <div class="ac-summary">{{ m.action.summary || '（无操作说明）' }}</div>
          <div class="ac-btns" v-if="m.actionState === 'pending'">
            <button class="ac-ok" :disabled="m.actionRunning" @click="runAction(m)">
              {{ m.actionRunning ? '执行中…' : '确认执行' }}
            </button>
            <button class="ac-no" :disabled="m.actionRunning" @click="cancelAction(m)">取消</button>
          </div>
          <div class="ac-state" :class="m.actionState" v-else>
            {{ m.actionState === 'done' ? '✓ 已执行' : '已取消' }}
          </div>
        </div>
      </div>
    </div>
    <div class="chat-input">
      <input v-model="inputText" placeholder="问点什么…" @keydown.enter="send">
      <button @click="send">发送</button>
    </div>

    <!-- 缩放手柄：右下角斜线角标，pointer capture 拖动调宽高 -->
    <div
      class="chat-resize-grip" title="拖动调整大小"
      @pointerdown="onGripDown" @pointermove="onGripMove"
      @pointerup="onGripUp" @pointercancel="onGripUp"
    ></div>

    <!-- 会话抽屉：面板内覆盖层，列表（标题 + 时间 + 条数），hover 出删除 ✕，顶部「+ 新对话」 -->
    <div class="chat-sessions" v-if="sessionsOpen">
      <div class="chat-sessions-head">
        <span>对话列表</span>
        <button @click="newSession">+ 新对话</button>
      </div>
      <div class="chat-sessions-list">
        <div
          class="chat-sess" v-for="s in sessions" :key="s.id"
          :class="{ active: s.id === currentSessionId }"
          @click="switchSession(s.id)"
        >
          <span class="t">{{ s.title }}</span>
          <span class="meta">{{ fmtTime(s.updated_at) }} · {{ s.message_count }} 条</span>
          <span class="del" title="删除该对话" @click.stop="removeSession(s)">✕</span>
        </div>
        <div class="chat-sess-empty" v-if="!sessions.length">暂无历史对话</div>
      </div>
    </div>
  </div>
</template>
