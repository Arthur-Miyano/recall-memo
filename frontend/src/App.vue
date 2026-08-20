<script setup>
// App 骨架
// 职责：顶部原型导航（router-link 版）+ 路由出口 + 全局水墨螃蟹（含对话面板）
// 数据流：导航项来自 router 配置的 meta.nav；螃蟹面板状态在 InkCrab 内部自管理
// 注意：记忆训练/面试答题不进顶部导航（meta.navHide）——只能从首页抽屉进入，
//       防止误触直达开始答题；路由本身保留
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import InkCrab from './components/InkCrab.vue'
import AgentTicker from './components/AgentTicker.vue'
import { offline } from './api'
import { startAgentEvents } from './utils/events'

const route = useRoute()
const router = useRouter()

// 订阅 /api/events（SSE）：实时显示当前活跃 Agent；断线由 EventSource 自动重连
onMounted(startAgentEvents)
</script>

<template>
  <!-- 原型导航：与 prototype/index.html 的 proto-nav 一致，高亮当前路由 -->
  <nav class="proto-nav">
    <span class="spacer"></span>
    <a
      v-for="r in router.getRoutes().filter(r => !r.meta.navHide)"
      :key="r.name"
      :class="{ on: route.name === r.name }"
      @click.prevent="router.push(r.path)"
      :href="r.path"
    >{{ r.meta.nav }}</a>
  </nav>

  <router-view />

  <!-- 全局水墨小螃蟹：固定左上角，点击开合对话面板 -->
  <InkCrab />

  <!-- 活跃 Agent 指示器：SSE 事件驱动，右下角，离线模式自动隐藏 -->
  <AgentTicker />

  <!-- 离线模式角标：后端不可达、页面回退 mock 演示数据时显示；下一次成功请求后自动消失 -->
  <div v-if="offline" class="offline-badge">离线模式 · 演示数据</div>
</template>

<style scoped>
/* 印章红细边 + mono 小字，固定左下角（避开左上角螃蟹与顶部导航），风格克制 */
.offline-badge {
  position: fixed;
  left: 16px;
  bottom: 16px;
  z-index: calc(var(--z-nav) + 1);
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: .08em;
  color: var(--seal);
  border: 1px solid var(--seal);
  border-radius: 2px;
  padding: 4px 10px;
  background: var(--paper-hi);
  pointer-events: none;
}
</style>
