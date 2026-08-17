<script setup>
// 划句右键存笔记：浮动菜单
// 用法：父组件 ref 拿到本组件，在可收藏文本的容器上监听 contextmenu：
//   const sel = window.getSelection()?.toString().trim()
//   if (sel) { e.preventDefault(); saver.open(e.clientX, e.clientY, sel, 来源题干) }
// 菜单内容：选中句子摘要 + 目标笔记列表（点击即存入）+ ＋ 新笔记
import { ref } from 'vue'
import { getNotes, createNote, appendNote } from '../api'

const visible = ref(false)
const pos = ref({ x: 0, y: 0 })
const text = ref('')        // 选中的句子
const source = ref('')      // 来源（题干）
const notes = ref([])
const loading = ref(false)
const busy = ref(false)
const savedTip = ref('')    // 存入成功提示（短暂显示后自动关）

async function open(x, y, selected, src) {
  text.value = selected
  source.value = src || ''
  // 钳制在视口内（菜单约 260px 宽）
  pos.value = { x: Math.min(x, window.innerWidth - 280), y: Math.min(y, window.innerHeight - 320) }
  visible.value = true
  savedTip.value = ''
  loading.value = true
  try {
    notes.value = (await getNotes()).items
  } catch (e) {
    console.warn('[note-saver] 笔记列表获取失败：', e.message)
    notes.value = []
  } finally {
    loading.value = false
  }
}

function close() { visible.value = false }

async function saveTo(note) {
  if (busy.value || savedTip.value) return
  busy.value = true
  try {
    await appendNote(note.id, text.value, source.value)
    savedTip.value = `已存入《${note.title}》`
    setTimeout(close, 900)
  } catch (e) {
    console.warn('[note-saver] 存笔记失败：', e.message)
    alert('存笔记失败：' + e.message)
  } finally {
    busy.value = false
  }
}

async function saveToNew() {
  if (busy.value || savedTip.value) return
  busy.value = true
  try {
    // 新笔记默认以来源题干（截 20 字）命名，方便日后回溯
    const title = source.value ? source.value.slice(0, 20) : '未命名笔记'
    const n = await createNote(title)
    await appendNote(n.id, text.value, source.value)
    savedTip.value = `已存入新笔记《${n.title}》`
    setTimeout(close, 900)
  } catch (e) {
    console.warn('[note-saver] 新建并存入失败：', e.message)
    alert('存笔记失败：' + e.message)
  } finally {
    busy.value = false
  }
}

defineExpose({ open, close })
</script>

<template>
  <!-- 透明遮罩：点击任意处关闭 -->
  <div v-if="visible" class="ns-overlay" @click="close" @contextmenu.prevent="close">
    <div class="ns-panel" :style="{ left: pos.x + 'px', top: pos.y + 'px' }" @click.stop>
      <div class="ns-quote">“{{ text.length > 50 ? text.slice(0, 50) + '…' : text }}”</div>
      <div class="ns-label">存入笔记</div>
      <div v-if="savedTip" class="ns-saved">{{ savedTip }}</div>
      <template v-else>
        <div v-if="loading" class="ns-dim">载入笔记 …</div>
        <template v-else>
          <button
            v-for="n in notes" :key="n.id"
            class="ns-item" :disabled="busy" @click="saveTo(n)"
          >{{ n.title }}</button>
          <div v-if="!notes.length" class="ns-dim">还没有笔记，存一篇新的 ↓</div>
          <button class="ns-item ns-new" :disabled="busy" @click="saveToNew">＋ 新笔记</button>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
.ns-overlay { position: fixed; inset: 0; z-index: calc(var(--z-nav) + 20); }
.ns-panel {
  position: fixed; width: 260px; max-height: 320px; overflow-y: auto;
  background: var(--paper-hi); border: 1px solid var(--ink);
  box-shadow: 5px 5px 0 var(--ink-12); padding: 14px;
}
.ns-quote {
  font-family: var(--serif); font-size: 13px; line-height: 1.7; color: var(--ink);
  border-left: 3px solid var(--ink); padding-left: 10px; margin-bottom: 12px;
}
.ns-label {
  font-family: var(--mono); font-size: 10px; letter-spacing: .14em;
  color: var(--ink-45); margin-bottom: 8px;
}
.ns-item {
  display: block; width: 100%; text-align: left; background: none;
  border: 1px solid var(--ink-12); padding: 8px 10px; margin-bottom: 6px;
  font-family: var(--serif); font-size: 13px; color: var(--ink); cursor: pointer;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: border-color .15s;
}
.ns-item:hover { border-color: var(--ink); }
.ns-new { border-style: dashed; color: var(--ink-45); }
.ns-new:hover { color: var(--ink); }
.ns-dim { font-family: var(--mono); font-size: 11px; color: var(--ink-45); padding: 6px 2px; }
.ns-saved {
  font-family: var(--serif); font-size: 14px; color: var(--seal);
  border: 1px solid var(--seal); padding: 10px; text-align: center;
}
</style>
