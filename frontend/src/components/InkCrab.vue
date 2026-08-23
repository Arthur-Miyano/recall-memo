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
// 结构：会话管理 / 拖动 / 吐泡泡 / 面板缩放 / 动作确认分别在 composables/useCrab*.js 与 useChatResize.js；
//       视口钳制纯计算在 utils/crabGeometry.js；本文件只做装配与对话发送
import { ref, computed, nextTick } from 'vue'
import { assistant } from '../mock/assistant'
import { assistantChat, offline } from '../api'
import { panelOffset } from '../utils/crabGeometry'
import { useCrabSessions } from '../composables/useCrabSessions'
import { useCrabDrag } from '../composables/useCrabDrag'
import { useCrabBubbles } from '../composables/useCrabBubbles'
import { useChatResize } from '../composables/useChatResize'
import { useCrabActions } from '../composables/useCrabActions'

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

function togglePanel() { panelShow.value = !panelShow.value }
function closePanel() { panelShow.value = false; sessionsOpen.value = false }

// 滚动到底部
async function scrollBottom() {
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
}

/* ---------- 独立职责拆分（§9.2）：各 composable 管自己的状态与副作用 ---------- */
const { bubbles, burst } = useCrabBubbles()
const { pos, dragging, onPointerDown, onPointerMove, onPointerUp } = useCrabDrag({ onTap: togglePanel, onDrop: burst })
const { panelSize, onGripDown, onGripMove, onGripUp } = useChatResize()
const {
  sessions, sessionsOpen, currentSessionId,
  switchSession, newSession, removeSession, toggleSessions, fmtTime,
} = useCrabSessions({ panelShow, messages, scrollBottom })
const { runAction, cancelAction, actionLabel } = useCrabActions({ messages, scrollBottom })

// 面板跟随螃蟹：水平对齐并钳制在视口内；螃蟹在下半屏时面板向上开，避免被裁掉
// 位置随 panelSize 一起钳制：调整后若超出视口则收回到可见范围
const panelStyle = computed(() => {
  const { w, h } = panelSize.value
  const { left, top } = panelOffset(pos.value, { w, h }, window.innerWidth, window.innerHeight)
  return { left: left + 'px', top: top + 'px', width: w + 'px', height: h + 'px' }
})

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
