<script setup>
// 仪表盘子组件：模型与密钥配置面板（FIG.04-F）
// 职责：PROVIDER 单选 + 模型名 + API KEY 输入 + 环境变量提取演示 + 红线说明
// 数据流：mock/dashboard.js → dashboard.settings（未来 GET/POST /api/settings/llm）
// 注意：密钥红线——仅写入本机 .env，接口只回掩码，不上传不外泄
import { ref } from 'vue'
import { dashboard } from '../mock/dashboard'

const s = dashboard.settings
const providerOn = ref(s.providerOn)
const model = ref(s.model)
const apiKey = ref('')
// 密钥状态：默认未配置；点「从环境变量提取」后显示掩码（演示）
const keyStatus = ref(null)

// 从环境变量提取（演示）：展示掩码后的 KEY
function pullFromEnv() {
  keyStatus.value = s.envPulled
}
</script>

<template>
  <div class="db-panel" id="settings-panel">
    <h2>模型与密钥配置 <span class="n">FIG.04-F</span></h2>
    <div class="set-row">
      <span class="lbl">PROVIDER</span>
      <div class="opt-group">
        <button
          v-for="(p, i) in s.providers"
          :key="p"
          class="opt"
          :class="{ on: providerOn === i }"
          @click="providerOn = i"
        >{{ p }}</button>
      </div>
    </div>
    <div class="set-row">
      <span class="lbl">模型</span>
      <input class="set-input" v-model="model">
    </div>
    <div class="set-row">
      <span class="lbl">API KEY</span>
      <input class="set-input" type="password" :placeholder="s.keyPlaceholder" v-model="apiKey">
    </div>
    <div class="set-row">
      <span class="lbl"></span>
      <button class="btn btn--ghost" style="padding:7px 18px;font-size:12px" @click="pullFromEnv">从环境变量提取</button>
      <span class="key-status" v-if="!keyStatus">当前：<b>{{ s.keyStatus }}</b></span>
      <span class="key-status" v-else>当前：<b>{{ keyStatus.name }}</b> {{ keyStatus.masked }}</span>
      <span style="flex:1"></span>
      <button class="btn" style="padding:7px 18px;font-size:12px">保存到本地</button>
    </div>
    <div class="set-note">
      <span class="seal">// 红线：KEY 不上传、不外泄</span><br>
      // 仅写入本机 .env；接口只回掩码（sk-••••81d7）；不入日志、不进 localStorage<br>
      // 唯一外发路径：后端 → 所选 PROVIDER 官方 API
    </div>
  </div>
</template>
