<script setup>
// 屏幕：题库总览
// 职责：顶部 Tab（全部 / 各技术栈胶囊）切换 + 技术栈 → 知识点两级分组 + 背诵状态格 + 线性进度 + 圈选重点背诵
// 数据流（真实接口，失败回退 mock/bank.js 并 console.warn）：
//   GET   /api/bank/overview            —— 分组 + 每题状态（done 掌握 / weak 薄弱·待补答 / todo 未背）
//   POST  /api/bank/focus               —— 圈选/取消「重点背诵」分组（持久化到后端）
//   PATCH /api/bank/questions/{id}      —— 编辑题目（题干/答案/技术栈/难度），保存后刷新总览
//   POST  /api/bank/questions/migrate   —— 多选迁移到目标栈（迁移模式下禁用编辑/删除入口）
// 交互：顶部 .opt 胶囊 Tab 切换技术栈（从接口数据动态生成，全局进度条固定不动）；点击分组头（.sub-head）切换 starred
// 动效：qcell hover 放大 + 悬停题目 tip（纯 CSS）
import { reactive, ref, computed, onMounted } from 'vue'
import { bankOverview } from '../mock/bank'
import { getBankOverview, postBankFocus, deleteBankQuestion } from '../api'
import { getStatsPerQuestion, patchBankQuestion, migrateBankQuestions } from '../api/bank'

// reactive 深拷贝，圈选状态可本地切换；真实数据到位后整体替换
const bank = reactive(JSON.parse(JSON.stringify(bankOverview)))

// 题格悬停 tooltip 用的完整题干（bank/overview 的 tip 是截断版，题格小看不出是哪道题）
const stemMap = ref({})
// 编辑弹层预填用的逐题完整信息（题干/答案/技术栈；难度接口未返回，弹层默认"不修改"）
const qInfoMap = ref({})

// 21 个 canonical 技术栈（key/显示名与后端 STACK_DISPLAY 一致）；自由命名栈允许手动输入
const COMMON_STACKS = [
  ['python', 'Python'], ['java', 'Java'], ['go', 'Go'], ['c', 'C'], ['cpp', 'C++'],
  ['csharp', 'C#'], ['php', 'PHP'], ['javascript', 'JavaScript'], ['vue3', 'Vue 3'],
  ['react', 'React'], ['database', 'Database'], ['network', '计算机网络'], ['os', '操作系统'],
  ['algorithm', '算法'], ['design_pattern', '设计模式'], ['distributed', '分布式'],
  ['linux', 'Linux'], ['devops', 'DevOps'], ['agent', 'Agent'], ['hr', 'HR'], ['other', '其他'],
].map(([key, name]) => ({ key, name }))
// 栈 key → 显示名；自由命名栈原样显示
const stackName = (key) => (COMMON_STACKS.find(s => s.key === key) || {}).name || key

// mock 数据没有 stack key，按名字补一个（真实数据自带 key）
const NAME2KEY = { Python: 'python', Agent: 'agent', 'Vue 3': 'vue3' }
const stackKey = (s) => s.key || NAME2KEY[s.name] || s.name

// 当前 Tab：'all' 或技术栈 key；从接口数据动态生成
const activeTab = ref('all')
const tabs = computed(() => [
  { key: 'all', name: '全部', total: bank.total, done: bank.done },
  ...(bank.stacks || []).map(s => ({ key: stackKey(s), name: s.name, total: s.total, done: s.done })),
])
// Tab 过滤后的技术栈分组
const visibleStacks = computed(() =>
  activeTab.value === 'all' ? bank.stacks : (bank.stacks || []).filter(s => stackKey(s) === activeTab.value)
)

// 拉取总览 + 逐题题干（删除题目成功后也走这里刷新）
async function refresh() {
  try {
    const d = await getBankOverview()
    bank.done = d.done
    bank.total = d.total
    bank.stacks = d.stacks
  } catch (e) {
    console.warn('[bank] 获取题库总览失败，回退 mock 数据：', e.message)
  }
  // 完整题干单独拉取，失败只影响悬停 tooltip / 编辑预填，不影响主界面
  try {
    const perQ = await getStatsPerQuestion()
    stemMap.value = Object.fromEntries(perQ.items.map(q => [q.question_id, q.stem]))
    qInfoMap.value = Object.fromEntries(perQ.items.map(q => [q.question_id, q]))
  } catch (e) {
    console.warn('[bank] 逐题题干获取失败（仅影响题格悬停提示）：', e.message)
  }
}

onMounted(refresh)

// 顶部线性进度：已背 / 总数（固定在顶部，不随 Tab 切换）
const pct = computed(() => (bank.total ? (bank.done / bank.total * 100).toFixed(0) : 0) + '%')

// 圈选/取消重点背诵分组：先本地切换，再持久化；失败回滚
async function toggleStar(stack, group) {
  group.starred = !group.starred
  try {
    await postBankFocus(stackKey(stack), group.name, group.starred)
  } catch (e) {
    group.starred = !group.starred
    console.warn('[bank] 圈选重点失败，已回滚：', e.message)
  }
}

// 删除题目：二次确认——第一次点 × 变红 "?"（3 秒不复位则自动复位），再点才真正删除
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
</script>

<template>
  <section class="screen active">
    <div class="bank-wrap">
      <div class="iv-topbar" style="margin-bottom:14px">
        <span>QUESTION BANK — 题库总览</span>
        <span class="spacer"></span>
        <span v-if="migrateMsg" style="color:var(--seal)">{{ migrateMsg }}</span>
        <span v-else>点击分组可圈选"重点背诵"</span>
        <button class="opt mig-toggle" :class="{ on: migrateMode }" @click="toggleMigrateMode">
          {{ migrateMode ? '退出迁移' : '迁移题目' }}
        </button>
      </div>
      <div class="bank-progress">
        <span class="mono" style="font-size:11px;letter-spacing:.12em;color:var(--ink-45)">已背诵</span>
        <div class="track"><i :style="{ width: pct }"></i></div>
        <span class="num">{{ bank.done }} / {{ bank.total }}</span>
      </div>

      <!-- 技术栈 Tab：胶囊风格（沿用 .opt 语言），从接口数据动态生成 -->
      <div class="opt-group bank-tabs" v-if="tabs.length > 2">
        <button
          class="opt"
          v-for="t in tabs"
          :key="t.key"
          :class="{ on: activeTab === t.key }"
          @click="activeTab = t.key"
        >{{ t.name }} · {{ t.done }}/{{ t.total }}</button>
      </div>

      <!-- 迁移模式操作条：已选计数 + 目标栈（21 常见栈 + 自由输入）+ 迁移/退出；点「迁移」后进入文本二次确认 -->
      <div class="mig-bar" v-if="migrateMode">
        <span class="mig-cnt">已选 {{ picked.size }} 题</span>
        <template v-if="!migrateConfirming">
          <select v-model="migrateSel" class="mig-input" title="目标技术栈">
            <option v-for="s in COMMON_STACKS" :key="s.key" :value="s.key">{{ s.name }}</option>
            <option value="__custom">自定义…</option>
          </select>
          <input
            v-if="migrateSel === '__custom'"
            v-model="migrateCustom"
            class="mig-input"
            placeholder="新栈名（小写英文）"
          />
          <button class="btn mig-btn" :disabled="!picked.size || !migrateTarget" @click="migrateConfirming = true">迁移</button>
          <button class="mig-link" @click="toggleMigrateMode">退出</button>
        </template>
        <template v-else>
          <span>将 {{ picked.size }} 道题迁移到 {{ stackName(migrateTarget) }}？</span>
          <button class="btn mig-btn" :disabled="migrating" @click="doMigrate">{{ migrating ? '迁移中…' : '确认' }}</button>
          <button class="mig-link" :disabled="migrating" @click="migrateConfirming = false">取消</button>
        </template>
        <span v-if="migrateError" class="mig-err">{{ migrateError }}</span>
      </div>

      <div class="bank-stack" v-for="stack in visibleStacks" :key="stack.name">
        <h3>{{ stack.name }} <span class="cnt">{{ stack.total }} 题 · 已背 {{ stack.done }}</span></h3>
        <div
          class="bank-sub"
          v-for="g in stack.groups"
          :key="g.name"
          :class="{ starred: g.starred }"
        >
          <div class="sub-head" @click="toggleStar(stack, g)">
            <span class="t">{{ g.name }}</span>
            <span class="mini">{{ g.cells.length }} 题</span>
            <span class="focus">{{ g.starred ? '重点背诵' : '+ 设为重点' }}</span>
          </div>
          <div class="cells">
            <div
              class="qcell"
              v-for="(c, ci) in g.cells"
              :key="c.question_id ?? ci"
              :class="{
                done: c.status === 'done',
                weak: c.status === 'weak',
                picking: migrateMode,
                picked: migrateMode && c.question_id != null && picked.has(c.question_id),
              }"
              :title="stemMap[c.question_id] || c.tip"
              @click="togglePick(c)"
            ><span class="tip">{{ c.tip }}</span><template
              v-if="!migrateMode && c.question_id != null"
            ><button
              class="qedit"
              title="编辑该题（题干/答案/技术栈/难度）"
              @click.stop="openEdit(c, stack)"
            >改</button><button
              class="qdel"
              :class="{ confirm: confirmingId === c.question_id }"
              :title="confirmingId === c.question_id ? '再点一次确认删除（连同答题记录）' : '删除该题'"
              @click.stop="onDeleteCell(c)"
            >{{ confirmingId === c.question_id ? '?' : '×' }}</button></template></div>
          </div>
        </div>
      </div>

      <div class="bank-legend">
        <span><i class="d"></i>已掌握</span>
        <span><i class="w"></i>薄弱 / 待补答</span>
        <span><i></i>未背诵</span>
        <span style="margin-left:auto">// 状态仅供你参考，Agent 抽题仍以真实表现为准</span>
      </div>
    </div>

    <!-- 编辑题目弹层：复用全局 .pm-* 弹层语言（半透纸色遮罩 + 墨边纸面 + 投影） -->
    <div class="pm-overlay" v-if="editing" @click.self="closeEdit">
      <div class="pm-paper qe-paper" role="dialog" aria-label="编辑题目">
        <div class="pm-head">
          <span class="fig">EDIT — 题 #{{ editing.id }}</span>
          <h2>编辑题目</h2>
          <button class="pm-close" title="关闭" @click="closeEdit">✕</button>
        </div>
        <div class="pm-body qe-body">
          <label class="qe-field">
            <span class="lbl">题干</span>
            <textarea v-model="editing.stem" rows="3"></textarea>
          </label>
          <label class="qe-field">
            <span class="lbl">答案</span>
            <textarea v-model="editing.answer" rows="6"></textarea>
          </label>
          <div class="qe-row">
            <label class="qe-field">
              <span class="lbl">技术栈</span>
              <select v-model="editing.stackSel">
                <option v-for="s in COMMON_STACKS" :key="s.key" :value="s.key">{{ s.name }}</option>
                <option value="__custom">自定义…</option>
              </select>
              <input
                v-if="editing.stackSel === '__custom'"
                v-model="editing.stackCustom"
                placeholder="新栈名（小写英文）"
              />
            </label>
            <label class="qe-field">
              <span class="lbl">难度</span>
              <select v-model="editing.difficulty">
                <option value="">不修改</option>
                <option value="basic">basic</option>
                <option value="medium">medium</option>
                <option value="hard">hard</option>
              </select>
            </label>
          </div>
          <p v-if="editing.error" class="qe-err">{{ editing.error }}</p>
        </div>
        <div class="pm-nav">
          <button @click="closeEdit">取消</button>
          <span class="idx">// 题干是录入判重的基准，改动会影响后续导入去重</span>
          <button class="qe-save" :disabled="editing.saving" @click="saveEdit">{{ editing.saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 题格删除入口：hover 才显示的迷你 ×（沿用墨水/印章红语言，不引入新组件） */
.qdel {
  display: none;
  position: absolute; top: -8px; right: -8px;
  width: 14px; height: 14px; padding: 0;
  border: 1px solid var(--ink); background: var(--paper-hi, #fff); color: var(--ink);
  font-size: 10px; line-height: 1; cursor: pointer; z-index: var(--z-stamp);
}
.qcell:hover .qdel { display: block; }
.qdel:hover { border-color: var(--seal); color: var(--seal); }
.qdel.confirm { display: block; background: var(--seal); border-color: var(--seal); color: var(--paper); }

/* 题格编辑入口：与 .qdel 同语言的迷你「改」（hover 显示，位于 × 左侧） */
.qedit {
  display: none;
  position: absolute; top: -8px; right: 8px;
  width: 14px; height: 14px; padding: 0;
  border: 1px solid var(--ink); background: var(--paper-hi, #fff); color: var(--ink);
  font-size: 9px; line-height: 1; cursor: pointer; z-index: var(--z-stamp);
}
.qcell:hover .qedit { display: block; }
.qedit:hover { background: var(--ink); color: var(--paper); }

/* 迁移模式开关：沿用 .opt 胶囊语言，与顶栏文字基线对齐 */
.mig-toggle { margin-left: 12px; }

/* 迁移操作条：墨边纸面条（与 .db-panel 同语言），不换行溢出时自动折行 */
.mig-bar {
  display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
  border: 1px solid var(--ink); background: var(--paper-hi);
  padding: 10px 14px; margin-bottom: 14px;
  font-family: var(--sans); font-size: 13px;
}
.mig-cnt { font-family: var(--mono); font-size: 11px; letter-spacing: .12em; color: var(--ink-45); }
.mig-input {
  font-family: var(--sans); font-size: 13px; padding: 4px 8px;
  border: 1px solid var(--ink-45); background: var(--paper); color: var(--ink);
}
.mig-input:focus { outline: none; border-color: var(--ink); }
.mig-btn { padding: 6px 16px; }
.mig-btn:disabled { opacity: .35; cursor: default; }
.mig-link {
  background: none; border: none; padding: 0; cursor: pointer;
  font-family: var(--sans); font-size: 12px; color: var(--ink-45); text-decoration: underline;
}
.mig-link:hover:not(:disabled) { color: var(--ink); }
.mig-err { color: var(--seal); font-size: 12px; }

/* 迁移模式下的题格：选中盖印章红描边 + ✓ 角标 */
.qcell.picked { outline: 2px solid var(--seal); outline-offset: 1px; }
.qcell.picked::after {
  content: '✓';
  position: absolute; top: -9px; right: -7px;
  width: 13px; height: 13px;
  background: var(--seal); color: var(--paper);
  font-size: 9px; line-height: 13px; text-align: center;
  z-index: var(--z-stamp);
}

/* 编辑弹层：骨架复用全局 .pm-*，这里只补表单字段样式 */
.qe-paper { width: min(640px, 100%); }
.qe-body { display: flex; flex-direction: column; gap: 14px; }
.qe-row { display: flex; gap: 16px; }
.qe-field { display: flex; flex-direction: column; gap: 6px; flex: 1; }
.qe-field .lbl { font-family: var(--mono); font-size: 10px; letter-spacing: .14em; color: var(--ink-45); }
.qe-field textarea, .qe-field select, .qe-field input {
  font-family: var(--sans); font-size: 13px; line-height: 1.7;
  border: 1px solid var(--ink-45); background: var(--paper); color: var(--ink);
  padding: 8px 10px;
}
.qe-field textarea { resize: vertical; }
.qe-field textarea:focus, .qe-field select:focus, .qe-field input:focus { outline: none; border-color: var(--ink); }
.qe-err { margin: 0; color: var(--seal); font-size: 12px; }
.qe-save { border-color: var(--seal) !important; color: var(--seal) !important; }
.qe-save:hover:not(:disabled) { background: var(--seal); color: var(--paper) !important; }
</style>
