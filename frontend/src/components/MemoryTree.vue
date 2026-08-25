<script setup>
// 记忆树：层级大纲递归渲染（节点 { title, note?, children?[] }），点带子节点的行折叠/展开
// 折叠状态集中在树根（provide/inject 共享一个 Set），纯逻辑见 utils/treeState.js
// 纸墨风：缩进 + 左侧细竖线（--ink-25），note 用 --ink-70 较小字号；折叠符号用文字字符 ▾/▸
import { computed, inject, provide, ref } from 'vue'
import { isCollapsed, nodeKey, toggleCollapsed } from '../utils/treeState.js'

const props = defineProps({
  node: { type: Object, required: true },    // 树节点：{ title, note?, children?[] }
  path: { type: Array, default: () => [] },  // 根到本节点的下标路径（折叠 key）
})

// 根节点（无注入）自建折叠集合并向下提供；子节点复用根的状态
const inherited = inject('memtree-collapsed', null)
const owned = inherited ? null : ref(new Set())
if (owned) provide('memtree-collapsed', owned)
const collapsed = inherited ?? owned

const key = nodeKey(props.path)
const kids = computed(() => props.node.children || [])
const folded = computed(() => isCollapsed(collapsed.value, key))

function toggle() {
  if (!kids.value.length) return
  collapsed.value = toggleCollapsed(collapsed.value, key)
}
</script>

<template>
  <div class="mt-node">
    <div class="mt-row" :class="{ 'mt-parent': kids.length }" @click="toggle">
      <span v-if="kids.length" class="mt-twisty">{{ folded ? '▸' : '▾' }}</span>
      <span class="mt-title">{{ node.title }}</span>
    </div>
    <div v-if="node.note" class="mt-note">{{ node.note }}</div>
    <div v-if="kids.length && !folded" class="mt-children">
      <MemoryTree v-for="(c, i) in kids" :key="i" :node="c" :path="[...path, i]" />
    </div>
  </div>
</template>

<style scoped>
.mt-row { display: flex; align-items: baseline; gap: 6px; }
.mt-row.mt-parent { cursor: pointer; }
.mt-twisty {
  flex: none; width: 12px; user-select: none;
  font-family: var(--mono); font-size: 11px; color: var(--ink-45);
}
.mt-title { font-size: 13.5px; line-height: 1.9; color: var(--ink); }
.mt-note { margin: 1px 0 4px 18px; font-size: 12px; line-height: 1.8; color: var(--ink-70); }
.mt-children { margin: 2px 0 4px 5px; padding-left: 12px; border-left: 1px solid var(--ink-25); }
</style>
