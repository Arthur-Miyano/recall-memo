<script setup>
// 录入题库面板（纸张 modal）
// 职责：粘贴文本 / 选择文件（.md/.txt/.json）→ 清洗去重开关 → 提交 → 展示结果清单
// 数据流：POST /api/bank/import（api/bank.js）→ {imported, skipped, enriched, errors}
//   入库 N 题：墨块对勾；跳过 M 题：附「与《xxx》相似 n%」；LLM 补全 K 题：标注 AI 生成字段
// 失败兜底：接口异常 console.warn + 面板内错误提示，不白屏
import { ref } from 'vue'
import DashboardModal from './DashboardModal.vue'
import { postBankImport } from '../api/bank'

const emit = defineEmits(['close', 'done'])

const text = ref('')
const dedupe = ref(true)      // 清洗去重开关，默认开
const loading = ref(false)    // 提交中（LLM 补全可能较慢）
const result = ref(null)      // 导入结果清单
const errorMsg = ref('')      // 接口级错误
const fileInput = ref(null)

const PLACEHOLDER = `格式说明：每题一段，题干必填；可选行：「答案：」「技术栈：」「知识点：」。
多题用空行或 --- 分隔。也支持 JSON：[{"question": "…", "answer": "…", "tech_stack": "python", "knowledge_point": "…"}]

示例：
Vue 3 的 v-show 和 v-if 有什么区别？
答案：v-if 是真实条件渲染……
技术栈：vue3
知识点：条件渲染`

// 选择文件：读文本内容填入 textarea（.json 也按文本读入，后端识别 JSON 数组）
function pickFile() { fileInput.value?.click() }
function onFile(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => { text.value = String(reader.result || '') }
  reader.onerror = () => { errorMsg.value = '文件读取失败' }
  reader.readAsText(file, 'utf-8')
  e.target.value = '' // 允许重复选同一文件
}

async function submit() {
  if (!text.value.trim() || loading.value) return
  loading.value = true
  result.value = null
  errorMsg.value = ''
  try {
    result.value = await postBankImport(text.value, dedupe.value)
    if (result.value.imported?.length) emit('done') // 有入库则通知仪表盘刷新
  } catch (e) {
    console.warn('[import] 录入题库失败：', e.message)
    errorMsg.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <DashboardModal title="录入题库" fig="IMPORT" @close="emit('close')">
    <textarea
      v-model="text"
      class="ip-textarea"
      :placeholder="PLACEHOLDER"
      :disabled="loading"
    ></textarea>

    <div class="ip-toolbar">
      <button class="ip-file-btn" :disabled="loading" @click="pickFile">选择文件（.md / .txt / .json）</button>
      <input ref="fileInput" type="file" accept=".md,.txt,.json" hidden @change="onFile" />
      <label class="ip-dedupe">
        <input type="checkbox" v-model="dedupe" :disabled="loading" />
        清洗去重
      </label>
      <span class="ip-note">开启后：与库内题目相似度 ≥85% 的题将被跳过；缺答案/分类的题由 AI 补全并标注</span>
      <button class="ip-submit" :disabled="loading || !text.trim()" @click="submit">
        {{ loading ? '清洗录入中…' : '开始录入' }}
      </button>
    </div>

    <div v-if="errorMsg" class="ip-result">
      <ul><li><span class="mk err">失败</span><span>{{ errorMsg }}</span></li></ul>
    </div>

    <div v-if="result" class="ip-result">
      <div class="sum">
        入库 {{ result.imported.length }} 题 · 跳过 {{ result.skipped.length }} 题 ·
        AI 补全 {{ result.enriched.length }} 题<span v-if="result.errors.length"> · 失败 {{ result.errors.length }} 题</span>
      </div>
      <ul>
        <li v-for="it in result.imported" :key="'i' + it.id">
          <span class="mk ok">■ 入库</span><span>{{ it.title }}</span><span class="why">{{ it.tech_stack }}</span>
        </li>
        <li v-for="(it, i) in result.skipped" :key="'s' + i">
          <span class="mk skip">□ 跳过</span><span>{{ it.title }}</span>
          <span class="why">与《{{ it.similar_to }}》相似 {{ it.similarity }}%</span>
        </li>
        <li v-for="(it, i) in result.enriched" :key="'e' + i">
          <span class="mk ai">✎ 补全</span><span>{{ it.title }}</span>
          <span class="why">AI 生成：{{ it.fields.join('、') }}</span>
        </li>
        <li v-for="(it, i) in result.errors" :key="'r' + i">
          <span class="mk err">✕ 失败</span><span>{{ it.title }}</span><span class="why">{{ it.reason }}</span>
        </li>
      </ul>
    </div>
  </DashboardModal>
</template>
