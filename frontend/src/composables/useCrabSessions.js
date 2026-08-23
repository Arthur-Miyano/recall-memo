// composable：水墨螃蟹的多会话管理（「≡ 对话」抽屉）
// 职责：会话列表拉取/切换/新建/删除 + 历史渲染；当前会话 id 存 localStorage（recall-chat-session）
// 参数：panelShow（首开时初始化会话列表）、messages（历史渲染写入）、scrollBottom（渲染后滚底）
import { ref, watch } from 'vue'
import { assistant } from '../mock/assistant'
import {
  getAssistantHistory,
  getAssistantSessions, createAssistantSession, deleteAssistantSession,
} from '../api'

export function useCrabSessions({ panelShow, messages, scrollBottom }) {
  const sessions = ref([])             // 会话列表（updated_at 倒序）
  const sessionsOpen = ref(false)      // 「≡ 对话」抽屉是否展开
  const currentSessionId = ref(null)   // 当前会话 id（localStorage 记忆）

  try {
    const saved = Number(localStorage.getItem('recall-chat-session'))
    if (Number.isInteger(saved) && saved > 0) currentSessionId.value = saved
  } catch { /* 损坏数据忽略 */ }

  let sessionsInited = false  // 会话列表只初始化一次；切换会话时单独拉历史

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

  return {
    sessions, sessionsOpen, currentSessionId,
    switchSession, newSession, removeSession, toggleSessions, fmtTime,
  }
}
