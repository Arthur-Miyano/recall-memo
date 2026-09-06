<script setup>
// 把答案文本渲染成可点查词的片段：英文单词带淡虚线下划线，点击弹单词卡片
import { computed } from 'vue'
import { splitWordSegments } from '../utils/wordText'
import { openWordCard } from '../utils/wordCardStore'

const props = defineProps({ text: { type: String, default: '' } })
const segs = computed(() => splitWordSegments(props.text))

function onWord(e, w) {
  e.stopPropagation() // 不触发卡片/模态框的点击关闭与放大
  openWordCard(w, e)
}
</script>

<template>
  <template v-for="(s, i) in segs" :key="i"><span
    v-if="s.kind === 'word'"
    class="w"
    @click="onWord($event, s.text)"
  >{{ s.text }}</span><template v-else>{{ s.text }}</template></template>
</template>
