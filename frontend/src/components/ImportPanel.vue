<script setup>
// 录入题库面板（纸张 modal）
// 职责：粘贴文本 / 多文件上传（.pdf/.md/.txt/.json）→ 后端后台任务录入 → 轮询进度 → 逐文件结果清单
// 数据流：POST /api/bank/import-jobs（FormData：files[] + text + dedupe）→ {job_id}
//   GET /api/bank/import-jobs/{id} 每 1.5s 轮询进度；
//   GET /api/bank/import-jobs/latest 打开面板时重挂：任务还在跑就继续显示进度
// 关键设计：录入在后端后台任务里执行，关闭面板/切换页面不中断；重开面板自动接上进度
import { ref, computed, onMounted, onUnmounted } from 'vue'
import DashboardModal from './DashboardModal.vue'
import { postBankImportJob, getBankImportJob, getBankImportJobLatest } from '../api/bank'

const emit = defineEmits(['close', 'done'])

const text = ref('')
const dedupe = ref(true)      // 清洗去重开关，默认开
const files = ref([])         // 待上传文件列表（多选）
const job = ref(null)         // 当前任务快照（running / done / error）
const errorMsg = ref('')      // 创建任务时的接口级错误
const fileInput = ref(null)
let timer = null

const running = computed(() => job.value?.status === 'running')
const result = computed(() => job.value?.result || null)

const PLACEHOLDER = `格式说明：每题一段，题干必填；可选行：「答案：」「技术栈：」「知识点：」。
多题用空行或 --- 分隔。也支持 JSON：[{"question": "…", "answer": "…", "tech_stack": "python", "knowledge_point": "…"}]

示例：
Vue 3 的 v-show 和 v-if 有什么区别？
答案：v-if 是真实条件渲染……
技术栈：vue3
知识点：条件渲染`

// 选择文件（可多选）：全部走后台任务上传，不再读进 textarea
function pickFile() { fileInput.value?.click() }
function onFile(e) {
  const picked = Array.from(e.target.files || [])
  e.target.value = '' // 允许重复选同一文件
  for (const f of picked) {
    if (!files.value.some(x => x.name === f.name && x.size === f.size)) files.value.push(f)
  }
}
function removeFile(i) { files.value.splice(i, 1) }
function formatKb(bytes) { return (bytes / 1024).toFixed(1) }

async function submit() {
  if (running.value) return
  if (!files.value.length && !text.value.trim()) return
  errorMsg.value = ''
  try {
    const d = await postBankImportJob({ files: files.value, text: text.value, dedupe: dedupe.value })
    job.value = {
      id: d.job_id, status: 'running', label: '', file_index: 0, file_count: 0,
      stage: '排队中', stage_done: 0, stage_total: 0,
    }
    startPolling(d.job_id)
  } catch (e) {
    console.warn('[import] 创建录入任务失败：', e.message)
    errorMsg.value = e.message
  }
}

function startPolling(id) {
  stopPolling()
  timer = setInterval(async () => {
    try {
      const j = await getBankImportJob(id)
      job.value = j
      if (j.status !== 'running') {
        stopPolling()
        if (j.status === 'done') {
          files.value = []
          text.value = ''
          if (j.result?.totals?.imported > 0) emit('done') // 有入库则通知仪表盘刷新
        }
      }
    } catch (e) {
      console.warn('[import] 轮询进度失败：', e.message)
      stopPolling()
    }
  }, 1500)
}
function stopPolling() { if (timer) { clearInterval(timer); timer = null } }

// 打开面板时接上最近任务：进行中的继续看进度，已完成的展示结果便于回看
onMounted(async () => {
  try {
    const { job: latest } = await getBankImportJobLatest()
    if (!latest) return
    job.value = latest
    if (latest.status === 'running') startPolling(latest.id)
  } catch (e) {
    console.warn('[import] 获取最近任务失败：', e.message)
  }
})
onUnmounted(stopPolling)

// 再来一批：清空任务视图，回到录入态
function resetAll() { job.value = null; errorMsg.value = '' }

const progressPct = computed(() => {
  const j = job.value
  if (!j || !j.stage_total) return 0
  return Math.min(100, Math.round((j.stage_done / j.stage_total) * 100))
})
</script>

<template>
  <DashboardModal title="录入题库" fig="IMPORT" @close="emit('close')">
    <!-- 录入态：无任务时显示 -->
    <template v-if="!job">
      <textarea
        v-model="text"
        class="ip-textarea"
        :placeholder="PLACEHOLDER"
      ></textarea>

      <!-- 已选文件列表（多选），可逐个移除 -->
      <ul v-if="files.length" class="ip-files">
        <li v-for="(f, i) in files" :key="f.name + f.size">
          <span class="ip-file-name">{{ f.name }}</span>
          <span class="ip-file-size">{{ formatKb(f.size) }} KB</span>
          <button class="ip-picked-clear" @click="removeFile(i)">✕ 移除</button>
        </li>
      </ul>

      <div class="ip-toolbar">
        <button class="ip-file-btn" @click="pickFile">选择文件（可多选 .pdf / .md / .txt / .json）</button>
        <input ref="fileInput" type="file" accept=".pdf,.md,.txt,.json" multiple hidden @change="onFile" />
        <label class="ip-dedupe">
          <input type="checkbox" v-model="dedupe" />
          清洗去重
        </label>
        <span class="ip-note">开启后：与库内题目相似度 ≥85% 的题将被跳过；缺答案/分类的题由 AI 补全并标注</span>
        <button class="ip-submit" :disabled="!files.length && !text.trim()" @click="submit">开始录入</button>
      </div>

      <div v-if="errorMsg" class="ip-result">
        <ul><li><span class="mk err">失败</span><span>{{ errorMsg }}</span></li></ul>
      </div>
    </template>

    <!-- 进行态：进度实时可见；关闭面板不中断，重开自动接上 -->
    <div v-else-if="running" class="ip-progress">
      <div class="sum">
        录入中<template v-if="job.file_count"> · 来源 {{ job.file_index }} / {{ job.file_count }}</template>
        <template v-if="job.label"> · {{ job.label }}</template>
      </div>
      <div class="ip-stage">{{ job.stage }}<template v-if="job.stage_total">（{{ job.stage_done }} / {{ job.stage_total }}）</template></div>
      <div class="ip-bar"><i :style="{ width: progressPct + '%' }"></i></div>
      <span class="ip-note">后台任务执行中：可以关闭此面板或切换页面，录入不会中断；重新打开本面板即可查看进度</span>
    </div>

    <!-- 完成态：总计 + 逐文件结果清单 -->
    <div v-else-if="job.status === 'done' && result" class="ip-result">
      <div class="sum">
        入库 {{ result.totals.imported }} 题 · 跳过 {{ result.totals.skipped }} 题 ·
        AI 补全 {{ result.totals.enriched }} 题<span v-if="result.totals.errors"> · 失败 {{ result.totals.errors }} 题</span>
      </div>
      <ul>
        <li v-for="fe in result.file_errors" :key="'fe' + fe.file">
          <span class="mk err">✕ 文件</span><span>{{ fe.file }}</span><span class="why">{{ fe.reason }}</span>
        </li>
      </ul>
      <div v-for="f in result.files" :key="f.file" class="ip-file-result">
        <div class="sum" v-if="result.files.length > 1">{{ f.file }}：入库 {{ f.imported.length }} · 跳过 {{ f.skipped.length }} · 补全 {{ f.enriched.length }}<span v-if="f.errors.length"> · 失败 {{ f.errors.length }}</span></div>
        <ul>
          <li v-for="it in f.imported" :key="'i' + it.id">
            <span class="mk ok">■ 入库</span><span>{{ it.title }}</span><span class="why">{{ it.tech_stack }}</span>
          </li>
          <li v-for="(it, i) in f.skipped" :key="'s' + i">
            <span class="mk skip">□ 跳过</span><span>{{ it.title }}</span>
            <span class="why">与《{{ it.similar_to }}》相似 {{ it.similarity }}%</span>
          </li>
          <li v-for="(it, i) in f.enriched" :key="'e' + i">
            <span class="mk ai">✎ 补全</span><span>{{ it.title }}</span>
            <span class="why">AI 生成：{{ it.fields.join('、') }}</span>
          </li>
          <li v-for="(it, i) in f.errors" :key="'r' + i">
            <span class="mk err">✕ 失败</span><span>{{ it.title }}</span><span class="why">{{ it.reason }}</span>
          </li>
        </ul>
      </div>
      <div class="ip-toolbar">
        <button class="ip-file-btn" @click="resetAll">再录入一批</button>
      </div>
    </div>

    <!-- 失败态 -->
    <div v-else class="ip-result">
      <ul><li><span class="mk err">失败</span><span>{{ job.error || '任务执行失败' }}</span></li></ul>
      <div class="ip-toolbar">
        <button class="ip-file-btn" @click="resetAll">重新录入</button>
      </div>
    </div>
  </DashboardModal>
</template>
