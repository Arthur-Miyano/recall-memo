<script setup>
// 屏幕七：笔记（文档式）
// 职责：背诵中划句收藏的片段在这里沉淀成笔记——左侧文档列表，右侧编辑器，自动保存
// 数据流（真实接口，失败 console.warn + 空态）：
//   GET    /api/notes            —— 列表（摘要，按最近编辑倒序）
//   POST   /api/notes            —— 新建
//   GET    /api/notes/{id}       —— 打开全文
//   PUT    /api/notes/{id}       —— 自动保存（标题/正文，防抖 800ms）
//   DELETE /api/notes/{id}       —— 删除
// 片段约定：背诵页划句右键收藏的内容以 "> 句子\n—— 来源题干" 引用块追加在文末
import { ref, watch, onMounted, nextTick } from 'vue'
import { getNotes, createNote, getNote, updateNote, deleteNote } from '../api'

const list = ref([])            // 摘要列表
const current = ref(null)       // 当前打开的全文 {id, title, content, ...}
const title = ref('')
const content = ref('')
const saveState = ref('')       // '' | '保存中…' | '已保存 HH:MM'
const listLoading = ref(true)

// ---- 列表 ----
async function loadList(selectId = null) {
  try {
    const d = await getNotes()
    list.value = d.items
    if (selectId != null) await openNote(selectId)
    else if (!current.value && d.items.length) await openNote(d.items[0].id)
  } catch (e) {
    console.warn('[notes] 笔记列表获取失败：', e.message)
  } finally {
    listLoading.value = false
  }
}
onMounted(loadList)

// ---- 打开一篇 ----
const opening = ref(false)
async function openNote(id) {
  if (opening.value || current.value?.id === id) return
  await flushSave()             // 切换前把上一篇的未存改动落盘
  opening.value = true
  try {
    const n = await getNote(id)
    current.value = n
    title.value = n.title
    content.value = n.content
    saveState.value = ''
    await nextTick()
    fitContent()
  } catch (e) {
    console.warn('[notes] 笔记打开失败：', e.message)
  } finally {
    opening.value = false
  }
}

// ---- 新建 ----
async function newNote() {
  try {
    const n = await createNote()
    await loadList(n.id)
    titleEl.value?.focus()
  } catch (e) {
    console.warn('[notes] 新建笔记失败：', e.message)
    alert('新建失败：' + e.message)
  }
}

// ---- 删除 ----
async function removeNote() {
  if (!current.value) return
  if (!confirm(`删除笔记《${current.value.title}》？此操作不可恢复。`)) return
  try {
    await deleteNote(current.value.id)
    current.value = null
    await loadList()
  } catch (e) {
    console.warn('[notes] 删除笔记失败：', e.message)
    alert('删除失败：' + e.message)
  }
}

// ---- 自动保存：标题/正文变更后防抖 800ms 落盘 ----
let saveTimer = null
watch([title, content], () => {
  if (!current.value || opening.value) return
  saveState.value = '保存中…'
  clearTimeout(saveTimer)
  saveTimer = setTimeout(flushSave, 800)
})
async function flushSave() {
  clearTimeout(saveTimer)
  if (!current.value || saveState.value !== '保存中…') return
  try {
    const n = await updateNote(current.value.id, { title: title.value, content: content.value })
    current.value = n
    const t = new Date()
    saveState.value = `已保存 ${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`
    // 同步列表摘要（标题/节选可能变了），不重排选中态
    const item = list.value.find(i => i.id === n.id)
    if (item) { item.title = n.title; item.excerpt = (n.content || '').replace(/\n/g, ' ').slice(0, 60) }
  } catch (e) {
    saveState.value = '保存失败'
    console.warn('[notes] 自动保存失败：', e.message)
  }
}

// ---- 正文框随内容撑高 ----
const titleEl = ref(null)
const contentEl = ref(null)
function fitContent() {
  const el = contentEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.max(420, el.scrollHeight) + 'px'
}

// 列表日期：M.DD
function fmtDay(iso) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}.${String(d.getDate()).padStart(2, '0')}`
}
</script>

<template>
  <section class="screen active">
    <div class="rv-head">
      <div>
        <div class="mono" style="font-size:11px;letter-spacing:.14em;color:var(--ink-45);margin-bottom:10px">NOTES — 知识归档</div>
        <h1 class="rv-title">笔记</h1>
      </div>
      <span class="spacer"></span>
      <div class="meta">背诵中划句右键即可收藏片段<br>相关性知识记到同一篇</div>
    </div>

    <div class="notes-layout">
      <!-- 左：文档列表 -->
      <aside class="notes-side">
        <button class="notes-new" @click="newNote">＋ 新笔记</button>
        <div v-if="listLoading" class="notes-empty-side">载入中 …</div>
        <div v-else-if="!list.length" class="notes-empty-side">还没有笔记</div>
        <div
          v-for="n in list" :key="n.id"
          class="note-item" :class="{ on: current?.id === n.id }"
          @click="openNote(n.id)"
        >
          <div class="ni-title">{{ n.title }}</div>
          <div class="ni-excerpt">{{ n.excerpt || '（空）' }}</div>
          <div class="ni-date">{{ fmtDay(n.updated_at) }}</div>
        </div>
      </aside>

      <!-- 右：编辑器 -->
      <div class="notes-main">
        <template v-if="current">
          <input ref="titleEl" class="ne-title" v-model="title" placeholder="未命名笔记">
          <div class="ne-meta">
            <span>FIG.07 — NOTE #{{ current.id }}</span>
            <span class="spacer"></span>
            <span class="ne-save" :class="{ bad: saveState === '保存失败' }">{{ saveState }}</span>
            <button class="ne-del" title="删除这篇笔记" @click="removeNote">删除</button>
          </div>
          <textarea
            ref="contentEl" class="ne-content" v-model="content"
            placeholder="从记忆训练中划句右键收藏片段，或直接在这里整理 …"
            @input="fitContent"
          ></textarea>
        </template>
        <div v-else class="notes-empty-main">
          <p>还没有打开的笔记</p>
          <p class="dim">点左侧「＋ 新笔记」开始；背诵时选中句子右键，也能直接存进来</p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 布局：左列表右编辑，飞书文档式；视觉沿用纸墨语言 */
.notes-layout { display: flex; gap: 28px; align-items: flex-start; }

/* ---- 左侧文档列表 ---- */
.notes-side { width: 280px; flex: none; display: flex; flex-direction: column; gap: 10px; }
.notes-new {
  width: 100%; padding: 12px 0; background: var(--ink); color: var(--paper);
  border: 1px solid var(--ink); font-family: var(--serif); font-size: 14px;
  letter-spacing: .1em; cursor: pointer; transition: opacity .15s;
}
.notes-new:hover { opacity: .85; }
.notes-empty-side { font-family: var(--mono); font-size: 11px; color: var(--ink-45); padding: 12px 4px; }
.note-item {
  position: relative; border: 1px solid var(--ink-12); background: var(--paper-hi);
  padding: 12px 14px 12px 18px; cursor: pointer; transition: border-color .15s;
}
.note-item:hover { border-color: var(--ink-45); }
.note-item.on { border-color: var(--ink); }
.note-item.on::before {   /* 选中篇左侧墨条 */
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--ink);
}
.ni-title {
  font-family: var(--serif); font-weight: 700; font-size: 15px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ni-excerpt {
  margin-top: 4px; font-size: 12px; color: var(--ink-45);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ni-date { margin-top: 6px; font-family: var(--mono); font-size: 10px; color: var(--ink-25); letter-spacing: .1em; }

/* ---- 右侧编辑器 ---- */
.notes-main {
  flex: 1; min-height: 560px; border: 1px solid var(--ink); background: var(--paper-hi);
  padding: 36px 44px 44px;
  box-shadow: 6px 6px 0 var(--ink-12);
}
.ne-title {
  width: 100%; border: none; border-bottom: 1px solid var(--ink-12); background: transparent;
  font-family: var(--serif); font-weight: 700; font-size: 28px; color: var(--ink);
  padding: 4px 0 12px; outline: none;
}
.ne-title:focus { border-bottom-color: var(--ink); }
.ne-meta {
  display: flex; align-items: center; gap: 14px; margin: 10px 0 22px;
  font-family: var(--mono); font-size: 10px; color: var(--ink-25); letter-spacing: .12em;
}
.ne-meta .spacer { flex: 1; }
.ne-save { color: var(--ink-45); }
.ne-save.bad { color: var(--seal); }
.ne-del {
  background: none; border: 1px solid var(--ink-25); color: var(--ink-45);
  font-family: var(--mono); font-size: 10px; letter-spacing: .12em; padding: 3px 10px; cursor: pointer;
  transition: color .15s, border-color .15s;
}
.ne-del:hover { color: var(--seal); border-color: var(--seal); }
.ne-content {
  width: 100%; min-height: 420px; border: none; background: transparent; resize: none; overflow: hidden;
  font-family: var(--sans); font-size: 15px; line-height: 2; color: var(--ink); outline: none;
  /* 稿纸横线 */
  background-image: repeating-linear-gradient(transparent 0 calc(2em - 1px), var(--ink-12) calc(2em - 1px) 2em);
}
.ne-content::placeholder { color: var(--ink-25); }

/* ---- 空态 ---- */
.notes-empty-main { padding: 80px 0; text-align: center; font-family: var(--serif); font-size: 17px; }
.notes-empty-main .dim { margin-top: 10px; font-family: var(--mono); font-size: 11px; color: var(--ink-45); letter-spacing: .06em; }

@media (max-width: 900px) {
  .notes-layout { flex-direction: column; }
  .notes-side { width: 100%; }
}
</style>
