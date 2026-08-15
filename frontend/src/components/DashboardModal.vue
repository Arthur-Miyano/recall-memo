<script setup>
// 仪表盘放大视图通用 modal（纸张风格）
// 职责：居中放大容器 —— 半透纸色遮罩 + 大纸面（墨边框 + 投影）
// 交互：点遮罩 / 点 ✕ / 按 Esc 关闭；打开时锁定背景滚动
// 动效：遮罩 screenIn 淡入，纸面 drop 落下（沿用 base.css 的既有动效语言）
import { onMounted, onUnmounted } from 'vue'

defineProps({
  title: { type: String, required: true }, // 宋体大标题，如「每日背诵记录」
  fig: { type: String, default: '' },      // mono 图注号，如 FIG.04-A
})
const emit = defineEmits(['close'])

function onKey(e) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => {
  window.addEventListener('keydown', onKey)
  document.body.style.overflow = 'hidden'
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  document.body.style.overflow = ''
})
</script>

<template>
  <div class="dm-overlay" @click.self="emit('close')">
    <div class="dm-paper" role="dialog" :aria-label="title">
      <div class="dm-head">
        <span v-if="fig" class="fig">{{ fig }}</span>
        <h2>{{ title }}</h2>
        <button class="dm-close" title="关闭（Esc）" @click="emit('close')">✕</button>
      </div>
      <div class="dm-body">
        <slot></slot>
      </div>
    </div>
  </div>
</template>
