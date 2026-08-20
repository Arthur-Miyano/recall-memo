<script setup>
// 活跃 Agent 指示器：SSE 收到活跃事件时显示「面试官 Agent 提问中…」，静默几秒后隐去
// 离线/mock 演示模式不显示（offline 见 api/index.js）；挂载于 App.vue 全局，右下角固定
import { computed } from 'vue'
import { offline } from '../api'
import { activeAgentEvent } from '../utils/events'

const visible = computed(() => !!activeAgentEvent.value && !offline.value)
</script>

<template>
  <Transition name="fade">
    <div v-if="visible" class="agent-ticker">
      <span class="dot"></span>
      {{ activeAgentEvent.agent }} Agent {{ activeAgentEvent.label }}
    </div>
  </Transition>
</template>

<style scoped>
/* 纸墨极简：mono 小字 + 细墨边 + 印章红脉动点，固定右下角（避开左下离线角标） */
.agent-ticker {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: calc(var(--z-nav) + 1);
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: .08em;
  color: var(--ink-70);
  border: 1px solid var(--ink-25);
  border-radius: 2px;
  padding: 4px 10px;
  background: var(--paper-hi);
  pointer-events: none;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--seal);
  animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse { 50% { opacity: .25; } }
.fade-enter-active, .fade-leave-active { transition: opacity .3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
