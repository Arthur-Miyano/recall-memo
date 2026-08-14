<script setup>
// App 骨架
// 职责：顶部原型导航（router-link 版）+ 路由出口 + 全局水墨螃蟹（含对话面板）
// 数据流：导航项来自 router 配置的 meta.nav；螃蟹面板状态在 InkCrab 内部自管理
import { useRoute, useRouter } from 'vue-router'
import InkCrab from './components/InkCrab.vue'

const route = useRoute()
const router = useRouter()
</script>

<template>
  <!-- 原型导航：与 prototype/index.html 的 proto-nav 一致，高亮当前路由 -->
  <nav class="proto-nav">
    <span class="spacer"></span>
    <a
      v-for="r in router.getRoutes()"
      :key="r.name"
      :class="{ on: route.name === r.name }"
      @click.prevent="router.push(r.path)"
      :href="r.path"
    >{{ r.meta.nav }}</a>
  </nav>

  <router-view />

  <!-- 全局水墨小螃蟹：固定左上角，点击开合对话面板 -->
  <InkCrab />
</template>
