<script setup>
// 单词卡片：背板同风格的迷你弹卡，跟随点击位置（靠近边缘自动收进视口）
import { computed, onMounted, onUnmounted } from 'vue'
import { wordCard, closeWordCard } from '../utils/wordCardStore'
import { speakWord } from '../utils/speak'

const style = computed(() => {
  const W = 340
  const H = 260 // 估算高度，用于贴边翻转到上方
  let x = Math.min(wordCard.x + 12, window.innerWidth - W - 16)
  let y = wordCard.y + 14
  if (y + H > window.innerHeight) y = Math.max(16, wordCard.y - H - 8)
  return { left: Math.max(16, x) + 'px', top: y + 'px' }
})

function onKey(e) {
  if (e.key === 'Escape') closeWordCard()
}
onMounted(() => {
  window.addEventListener('click', closeWordCard)
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => {
  window.removeEventListener('click', closeWordCard)
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div v-if="wordCard.visible" class="word-card" :style="style" @click.stop>
    <div class="wc-head">
      <h4>{{ wordCard.loading || !wordCard.found ? wordCard.query : wordCard.word }}</h4>
      <button class="wc-say" title="朗读" @click="speakWord(wordCard.query)">🔊</button>
      <button class="wc-close" title="关闭（Esc）" @click="closeWordCard">×</button>
    </div>
    <p class="wc-pho" v-if="wordCard.phonetic">/{{ wordCard.phonetic }}/</p>
    <div v-if="wordCard.loading" class="wc-body wc-dim">查询中…</div>
    <div v-else-if="wordCard.error" class="wc-body wc-dim">{{ wordCard.error }}</div>
    <div v-else-if="!wordCard.found" class="wc-body wc-dim">词典未收录这个词（可能是技术术语或缩写）。</div>
    <div v-else class="wc-body">
      <p v-if="wordCard.word.toLowerCase() !== wordCard.query.toLowerCase()" class="wc-lemma">
        原型：{{ wordCard.word }}
      </p>
      {{ wordCard.translation }}
    </div>
  </div>
</template>
