<script setup>
// 仪表盘子组件：模型与密钥配置面板（FIG.04-F）
// 职责：PROVIDER 单选 + 模型名 + API KEY 输入 + 环境变量检测 + 红线说明
// 数据流（真实接口，失败回退 mock/dashboard.js 并 console.warn）：
//   GET  /api/settings/llm  —— provider / 模型名 / Key 掩码与配置状态 / 环境变量检测
//   POST /api/settings/llm  —— 保存 provider + 模型名 + Key（仅写本机 .env，响应只回掩码）
// 注意：密钥红线——仅写入本机 .env，接口只回掩码，不上传不外泄
import { ref, computed, onMounted } from 'vue'
import { dashboard } from '../mock/dashboard'
import { getLlmSettings, postLlmSettings, importDatabase } from '../api'

const s = dashboard.settings
// Provider 展示名 ↔ 后端 key（key 为 null 表示未接入，按钮置灰）
const PROVIDERS = [
  { label: 'DEEPSEEK', key: 'deepseek' },
  { label: 'KIMI', key: 'kimi' },
  { label: '智谱', key: 'zhipu' },
  { label: '豆包', key: 'doubao' },
]
// 各 Provider 的常用模型建议（datalist 提示，仍可自由输入其他型号/接入点 ID）
const MODEL_SUGGESTIONS = {
  deepseek: ['deepseek-v4-flash', 'deepseek-v4-pro'],
  kimi: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'],
  zhipu: ['glm-4.7-flash', 'glm-4.5-flash'],
  doubao: ['doubao-seed-2-0-mini-260428', 'doubao-seed-1-6-flash-250828'],
}
const providerOn = ref(s.providerOn)
const model = ref(s.model)
const apiKey = ref('')
// 密钥状态：{ name, masked }；null 时显示「未配置/已配置」
const keyStatus = ref(null)
const keyConfigured = ref(false)
const saving = ref(false)

const providerKey = computed(() => PROVIDERS[providerOn.value]?.key)

onMounted(async () => {
  try {
    const d = await getLlmSettings()
    applySettings(d)
  } catch (e) {
    console.warn('[settings] 获取配置失败，回退 mock 展示：', e.message)
  }
})

// 应用接口返回的配置到面板
function applySettings(d) {
  const idx = PROVIDERS.findIndex(p => p.key === d.provider)
  if (idx >= 0) providerOn.value = idx
  model.value = d.model
  keyConfigured.value = d.key_configured
  keyStatus.value = d.key_masked
    ? { name: `${(d.provider || '').toUpperCase()}_API_KEY（.env）`, masked: d.key_masked }
    : null
}

// 从环境变量提取：后端检测 os.environ 里是否已有该 Provider 的 Key（只回掩码）
async function pullFromEnv() {
  if (!providerKey.value) return
  try {
    const d = await getLlmSettings()
    const hit = d.env_detected?.[providerKey.value]
    keyStatus.value = hit?.masked
      ? { name: `${hit.env_var}（环境变量）`, masked: hit.masked }
      : { name: `${hit?.env_var || ''}（环境变量）`, masked: '未检测到' }
  } catch (e) {
    console.warn('[settings] 环境变量检测失败：', e.message)
  }
}

// 保存到本地：写 .env + 热更新 LLM 路由；Key 留空表示不修改
async function save() {
  if (!providerKey.value) { alert('该 Provider 暂未接入'); return }
  saving.value = true
  try {
    const d = await postLlmSettings({
      provider: providerKey.value,
      model: model.value || undefined,
      api_key: apiKey.value || undefined,
    })
    applySettings(d)
    apiKey.value = ''
  } catch (e) {
    console.warn('[settings] 保存失败：', e.message)
    alert('保存失败：' + e.message)
  } finally {
    saving.value = false
  }
}

/* ---------- 数据备份与迁移 ---------- */
const fileInput = ref(null)
const importFile = ref(null)
const importing = ref(false)
const importResult = ref(null)

function onPick(e) {
  importFile.value = e.target.files[0] || null
  importResult.value = null
}

// 导入旧环境的 .db 备份：后端自动备份当前数据后幂等合并，重复导入不产生重复数据
async function doImport() {
  if (!importFile.value) return
  importing.value = true
  try {
    const form = new FormData()
    form.append('file', importFile.value)
    importResult.value = await importDatabase(form)
  } catch (e) {
    console.warn('[settings] 导入失败：', e.message)
    alert('导入失败：' + e.message)
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <div class="db-panel" id="settings-panel">
    <h2>模型与密钥配置 <span class="n">FIG.04-F</span></h2>
    <div class="set-row">
      <span class="lbl">PROVIDER</span>
      <div class="opt-group">
        <button
          v-for="(p, i) in PROVIDERS"
          :key="p.label"
          class="opt"
          :class="{ on: providerOn === i }"
          :disabled="!p.key"
          :title="p.key ? '' : '暂未接入'"
          @click="providerOn = i"
        >{{ p.label }}</button>
      </div>
    </div>
    <div class="set-row">
      <span class="lbl">模型</span>
      <input class="set-input" v-model="model" list="model-suggestions">
      <datalist id="model-suggestions">
        <option v-for="m in MODEL_SUGGESTIONS[providerKey] || []" :key="m" :value="m" />
      </datalist>
    </div>
    <div class="set-row">
      <span class="lbl">API KEY</span>
      <input class="set-input" type="password" :placeholder="s.keyPlaceholder" v-model="apiKey">
    </div>
    <div class="set-row">
      <span class="lbl"></span>
      <button class="btn btn--ghost" style="padding:7px 18px;font-size:12px" @click="pullFromEnv">从环境变量提取</button>
      <span class="key-status" v-if="!keyStatus">当前：<b>{{ keyConfigured ? '已配置' : s.keyStatus }}</b></span>
      <span class="key-status" v-else>当前：<b>{{ keyStatus.name }}</b> {{ keyStatus.masked }}</span>
      <span style="flex:1"></span>
      <button class="btn" style="padding:7px 18px;font-size:12px" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存到本地' }}</button>
    </div>
    <div class="set-note">
      <span class="seal">// 红线：KEY 不上传、不外泄</span><br>
      // 仅写入本机 .env；接口只回掩码（sk-••••81d7）；不入日志、不进 localStorage<br>
      // 唯一外发路径：后端 → 所选 PROVIDER 官方 API
    </div>
  </div>

  <div class="db-panel" id="datamove-panel" style="margin-top:24px">
    <h2>数据备份与迁移 <span class="n">FIG.04-G</span></h2>
    <div class="set-row">
      <span class="lbl">导出</span>
      <a class="btn btn--ghost" style="padding:7px 18px;font-size:12px;text-decoration:none" href="/api/settings/export" download>导出数据</a>
      <span class="key-status">下载完整数据文件（题库 + 背诵记录 + 笔记）</span>
    </div>
    <div class="set-row">
      <span class="lbl">导入</span>
      <input ref="fileInput" type="file" accept=".db" style="display:none" @change="onPick">
      <button class="btn btn--ghost" style="padding:7px 18px;font-size:12px" @click="fileInput.click()">选择备份文件</button>
      <span class="key-status" v-if="importFile">{{ importFile.name }}</span>
      <span style="flex:1"></span>
      <button class="btn" style="padding:7px 18px;font-size:12px" :disabled="!importFile || importing" @click="doImport">{{ importing ? '导入中…' : '确认导入' }}</button>
    </div>
    <div class="set-note" v-if="importResult">
      <span class="seal">// 合并完成</span><br>
      <template v-for="(t, name) in importResult.tables" :key="name">// {{ name }}：导入 {{ t.imported }}，跳过 {{ t.skipped }}<br></template>
      <template v-if="importResult.backup">// 导入前备份：{{ importResult.backup }}</template>
    </div>
    <div class="set-note">
      <span class="seal">// 换新电脑 / 新版本时用</span><br>
      // 旧环境导出 → 新环境导入，题库和背诵记录全部带过来<br>
      // 导入前自动备份当前数据；同一份文件重复导入不会产生重复数据
    </div>
  </div>
</template>
