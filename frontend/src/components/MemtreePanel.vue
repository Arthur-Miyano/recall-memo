<script setup>
// 记忆树提取面板（纸张 modal）
// 职责：各栈覆盖统计表格 → 选范围/模式 → 后端后台任务批量生成 → 轮询进度 → 成功/失败汇总
// 数据流：GET /api/memtree/status（打开时 + 任务完成后刷新）；
//   POST /api/memtree/jobs {stack?, regenerate} → {job_id}；
//   GET /api/memtree/jobs/{id} 每 1.5s 轮询进度；
//   GET /api/memtree/jobs/latest 打开面板时重挂：任务还在跑就继续显示进度
// 关键设计：生成在后端后台任务里执行，关闭面板/切换页面不中断；重开面板自动接上进度
import { ref, computed, onMounted, onUnmounted } from 'vue'
import DashboardModal from './DashboardModal.vue'
import { getMemtreeStatus, postMemtreeJob, getMemtreeJob, getMemtreeJobLatest } from '../api/memtree'

const emit = defineEmits(['close'])

const status = ref(null)      // {stacks: [...], total: {...}} 覆盖统计
const stack = ref('')         // 选中的技术栈（'' = 全部栈）
const regenerate = ref(false) // true = 范围内全部重新生成；false = 只补缺树
const job = ref(null)         // 当前任务快照（running / done / error）
const errorMsg = ref('')      // 创建任务时的接口级错误
let timer = null

const running = computed(() => job.value?.status === 'running')
const result = computed(() => job.value?.result || null)

// 当前选中范围的统计行（全部栈时用总计行）
const scope = computed(() => {
  if (!status.value) return null
  if (!stack.value) return status.value.total
  return status.value.stacks.find(g => g.tech_stack === stack.value) || null
})
// 本次将处理的题数：重新生成 = 范围内全部；只补缺 = 缺树数
const scopeCount = computed(() => {
  if (!scope.value) return 0
  return regenerate.value ? scope.value.total : scope.value.missing
})

async function loadStatus() {
  try {
    status.value = await getMemtreeStatus()
  } catch (e) {
    console.warn('[memtree] 获取覆盖统计失败：', e.message)
  }
}

async function submit() {
  if (running.value) return
  if (scopeCount.value <= 0) return
  errorMsg.value = ''
  try {
    const d = await postMemtreeJob({ stack: stack.value, regenerate: regenerate.value })
    job.value = {
      id: d.job_id, status: 'running', label: '',
      stage: '生成记忆树', stage_done: 0, stage_total: scopeCount.value,
    }
    startPolling(d.job_id)
  } catch (e) {
    console.warn('[memtree] 创建生成任务失败：', e.message)
    errorMsg.value = e.message
  }
}

function startPolling(id) {
  stopPolling()
  timer = setInterval(async () => {
    try {
      const j = await getMemtreeJob(id)
      job.value = j
      if (j.status !== 'running') {
        stopPolling()
        if (j.status === 'done') loadStatus() // 完成后刷新覆盖统计表格
      }
    } catch (e) {
      console.warn('[memtree] 轮询进度失败：', e.message)
      stopPolling()
    }
  }, 1500)
}
function stopPolling() { if (timer) { clearInterval(timer); timer = null } }

// 打开面板时：拉覆盖统计 + 接上最近任务（进行中的继续看进度，已完成的展示结果便于回看）
onMounted(async () => {
  loadStatus()
  try {
    const { job: latest } = await getMemtreeJobLatest()
    if (!latest) return
    job.value = latest
    if (latest.status === 'running') startPolling(latest.id)
  } catch (e) {
    console.warn('[memtree] 获取最近任务失败：', e.message)
  }
})
onUnmounted(stopPolling)

// 再跑一批：清空任务视图，回到选择态
function resetAll() { job.value = null; errorMsg.value = '' }

const progressPct = computed(() => {
  const j = job.value
  if (!j || !j.stage_total) return 0
  return Math.min(100, Math.round((j.stage_done / j.stage_total) * 100))
})
</script>

<template>
  <DashboardModal title="记忆树提取" fig="MEMTREE" @close="emit('close')">
    <!-- 各栈覆盖统计 -->
    <table v-if="status" class="dm-table">
      <thead><tr><th>技术栈</th><th>总题数</th><th>已有树</th><th>缺树</th></tr></thead>
      <tbody>
        <tr v-for="g in status.stacks" :key="g.tech_stack">
          <td>{{ g.tech_stack }}</td>
          <td class="mono">{{ g.total }}</td>
          <td class="mono">{{ g.with_tree }}</td>
          <td class="mono" :class="{ dim: !g.missing }">{{ g.missing }}</td>
        </tr>
        <tr v-if="!status.stacks.length"><td colspan="4" class="dim">题库暂无题目</td></tr>
        <tr v-if="status.stacks.length">
          <td class="mono">合计</td>
          <td class="mono">{{ status.total.total }}</td>
          <td class="mono">{{ status.total.with_tree }}</td>
          <td class="mono">{{ status.total.missing }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="dm-empty">统计数据暂未备好（接口异常详见控制台）</div>

    <!-- 选择态：无任务时显示 -->
    <template v-if="!job">
      <div class="ip-toolbar">
        <select v-model="stack" class="mt-select" title="技术栈范围">
          <option value="">全部技术栈</option>
          <option v-for="g in status?.stacks || []" :key="g.tech_stack" :value="g.tech_stack">
            {{ g.tech_stack }}（缺 {{ g.missing }}）
          </option>
        </select>
        <label class="ip-dedupe">
          <input type="radio" :value="false" v-model="regenerate" />
          只补缺树
        </label>
        <label class="ip-dedupe">
          <input type="radio" :value="true" v-model="regenerate" />
          重新生成范围内全部
        </label>
        <span class="ip-note">记忆树把标准答案重组为层级大纲辅助背诵；每批 5 题走一次 AI 调用，题多时耗时较长</span>
        <button class="ip-submit" :disabled="scopeCount <= 0" @click="submit">
          开始提取<template v-if="scopeCount > 0">（{{ scopeCount }} 题）</template>
        </button>
      </div>
      <div v-if="scopeCount <= 0 && status" class="ip-result">
        <ul><li><span class="mk ok">已就绪</span><span>当前范围内没有需要生成的题目</span></li></ul>
      </div>
      <div v-if="errorMsg" class="ip-result">
        <ul><li><span class="mk err">失败</span><span>{{ errorMsg }}</span></li></ul>
      </div>
    </template>

    <!-- 进行态：进度实时可见；关闭面板不中断，重开自动接上 -->
    <div v-else-if="running" class="ip-progress">
      <div class="sum">生成中<template v-if="job.label"> · {{ job.label }}</template></div>
      <div class="ip-stage">{{ job.stage }}<template v-if="job.stage_total">（{{ job.stage_done }} / {{ job.stage_total }}）</template></div>
      <div class="ip-bar"><i :style="{ width: progressPct + '%' }"></i></div>
      <span class="ip-note">后台任务执行中：可以关闭此面板或切换页面，生成不会中断；重新打开本面板即可查看进度</span>
    </div>

    <!-- 完成态：成功/失败汇总 -->
    <div v-else-if="job.status === 'done' && result" class="ip-result">
      <div class="sum">成功 {{ result.done }} 题<span v-if="result.failed"> · 失败 {{ result.failed }} 题</span></div>
      <ul>
        <li v-if="result.failed">
          <span class="mk err">× 失败</span>
          <span>{{ result.failed }} 题未生成</span>
          <span class="why">题号 {{ result.failed_ids.join('、') }}（可再跑一次补缺）</span>
        </li>
        <li v-else><span class="mk ok">■ 完成</span><span>范围内的题目都已挂上记忆树</span></li>
      </ul>
      <div class="ip-toolbar">
        <button class="ip-file-btn" @click="resetAll">再跑一批</button>
      </div>
    </div>

    <!-- 失败态 -->
    <div v-else class="ip-result">
      <ul><li><span class="mk err">失败</span><span>{{ job.error || '任务执行失败' }}</span></li></ul>
      <div class="ip-toolbar">
        <button class="ip-file-btn" @click="resetAll">重新提取</button>
      </div>
    </div>
  </DashboardModal>
</template>
