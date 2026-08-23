// composable：题库总览的编辑 / 删除 / 多选迁移工作流
// 职责：删除二次确认（× → ? → 真删）、编辑弹层（预填 + PATCH 保存）、
//       多选迁移模式（圈选 → 目标栈 → 文本二次确认 → POST migrate）
// 参数：refresh（写操作成功后重拉总览）、stackKey（分组 → 栈 key）、stemMap/qInfoMap（编辑预填）
import { ref, computed } from 'vue'
import { deleteBankQuestion } from '../api'
import { patchBankQuestion, migrateBankQuestions } from '../api/bank'

// 21 个 canonical 技术栈（key/显示名与后端 STACK_DISPLAY 一致）；自由命名栈允许手动输入
export const COMMON_STACKS = [
  ['python', 'Python'], ['java', 'Java'], ['go', 'Go'], ['c', 'C'], ['cpp', 'C++'],
  ['csharp', 'C#'], ['php', 'PHP'], ['javascript', 'JavaScript'], ['vue3', 'Vue 3'],
  ['react', 'React'], ['database', 'Database'], ['network', '计算机网络'], ['os', '操作系统'],
  ['algorithm', '算法'], ['design_pattern', '设计模式'], ['distributed', '分布式'],
  ['linux', 'Linux'], ['devops', 'DevOps'], ['agent', 'Agent'], ['hr', 'HR'], ['other', '其他'],
].map(([key, name]) => ({ key, name }))
// 栈 key → 显示名；自由命名栈原样显示
export const stackName = (key) => (COMMON_STACKS.find(s => s.key === key) || {}).name || key

export function useBankEditor({ refresh, stackKey, stemMap, qInfoMap }) {
  /* ---------- 删除题目：二次确认——第一次点 × 变红 "?"（3 秒不复位则自动复位），再点才真正删除 ---------- */
  const confirmingId = ref(null)
  let confirmTimer = null
  async function onDeleteCell(c) {
    if (confirmingId.value !== c.question_id) {
      confirmingId.value = c.question_id
      clearTimeout(confirmTimer)
      confirmTimer = setTimeout(() => { confirmingId.value = null }, 3000)
      return
    }
    clearTimeout(confirmTimer)
    confirmingId.value = null
    try {
      await deleteBankQuestion(c.question_id)
      await refresh()
    } catch (e) {
      console.warn('[bank] 删除题目失败：', e.message)
    }
  }

  /* ---------- 编辑题目（轻量弹层，复用全局 .pm-* 弹层语言） ---------- */
  // editing：null=关闭；否则 {id, stem, answer, stackSel, stackCustom, difficulty, saving, error}
  // stackSel === '__custom' 时取 stackCustom（自由命名新栈）；difficulty 空串 = 不修改
  const editing = ref(null)
  function openEdit(c, stack) {
    if (migrateMode.value || c.question_id == null) return
    const info = qInfoMap.value[c.question_id] || {}
    const cur = info.tech_stack || stackKey(stack)
    const known = COMMON_STACKS.some(s => s.key === cur)
    editing.value = {
      id: c.question_id,
      stem: info.stem ?? (stemMap.value[c.question_id] || ''),
      answer: info.answer ?? '',
      stackSel: known ? cur : '__custom',
      stackCustom: known ? '' : cur,
      difficulty: '',
      saving: false,
      error: '',
    }
  }
  function closeEdit() { if (!editing.value?.saving) editing.value = null }
  async function saveEdit() {
    const e = editing.value
    if (!e || e.saving) return
    if (!e.stem.trim()) { e.error = '题干不能为空'; return }
    const stack = e.stackSel === '__custom' ? e.stackCustom.trim() : e.stackSel
    const body = { stem: e.stem, answer: e.answer }
    if (stack) body.tech_stack = stack
    if (e.difficulty) body.difficulty = e.difficulty
    e.saving = true
    e.error = ''
    try {
      await patchBankQuestion(e.id, body)
      editing.value = null
      await refresh()
    } catch (err) {
      console.warn('[bank] 编辑题目失败：', err.message)
      e.error = err.message
      e.saving = false
    }
  }

  /* ---------- 多选迁移模式 ---------- */
  const migrateMode = ref(false)
  const picked = ref(new Set())          // 选中的 question_id 集合（替换式更新保证响应式）
  const migrateSel = ref('python')       // 目标栈下拉；'__custom' = 自由输入
  const migrateCustom = ref('')
  const migrateConfirming = ref(false)   // 二次确认：显示"将 N 道题迁移到 X？"
  const migrateMsg = ref('')             // 迁移结果提示（顶部工具区展示，下次进入迁移模式时清掉）
  const migrateError = ref('')
  const migrating = ref(false)

  const migrateTarget = computed(() =>
    migrateSel.value === '__custom' ? migrateCustom.value.trim() : migrateSel.value
  )

  function toggleMigrateMode() {
    migrateMode.value = !migrateMode.value
    picked.value = new Set()
    migrateConfirming.value = false
    migrateError.value = ''
    confirmingId.value = null            // 同时退出进行中的删除确认，避免状态打架
    if (migrateMode.value) migrateMsg.value = ''
  }
  function togglePick(c) {
    if (!migrateMode.value || c.question_id == null) return
    const s = new Set(picked.value)
    if (s.has(c.question_id)) s.delete(c.question_id)
    else s.add(c.question_id)
    picked.value = s
  }
  async function doMigrate() {
    if (migrating.value || !migrateTarget.value) return
    migrating.value = true
    migrateError.value = ''
    try {
      const res = await migrateBankQuestions([...picked.value], migrateTarget.value)
      migrateMsg.value = `已迁移 ${res.moved} 题 → ${stackName(res.to_stack)}`
        + (res.missing.length ? `（${res.missing.length} 题不存在，已跳过）` : '')
      toggleMigrateMode()                // 成功后退出迁移模式
      await refresh()
    } catch (e) {
      console.warn('[bank] 迁移题目失败：', e.message)
      migrateError.value = e.message
      migrateConfirming.value = false
    } finally {
      migrating.value = false
    }
  }

  return {
    confirmingId, onDeleteCell,
    editing, openEdit, closeEdit, saveEdit,
    migrateMode, picked, migrateSel, migrateCustom, migrateConfirming,
    migrateMsg, migrateError, migrating, migrateTarget,
    toggleMigrateMode, togglePick, doMigrate,
  }
}
