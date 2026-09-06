// 单词卡片的页面级共享状态：同一时间只有一张卡，WordText 触发打开，WordCard 渲染
import { reactive } from 'vue'
import { request } from '../api'
import { speakWord } from './speak'

export const wordCard = reactive({
  visible: false,
  x: 0,
  y: 0,
  query: '',
  loading: false,
  found: false,
  word: '',
  phonetic: '',
  translation: '',
  error: '',
})

let seq = 0 // 快速连点时只认最后一次查询

export async function openWordCard(word, event) {
  wordCard.visible = true
  wordCard.x = event.clientX
  wordCard.y = event.clientY
  wordCard.query = word
  wordCard.loading = true
  wordCard.found = false
  wordCard.word = ''
  wordCard.phonetic = ''
  wordCard.translation = ''
  wordCard.error = ''
  speakWord(word) // 点开即读一遍，卡片里按钮可重播
  const my = ++seq
  try {
    const d = await request(`/api/words/${encodeURIComponent(word)}`, { timeout: 10_000 })
    if (my !== seq) return // 期间又点了别的词
    wordCard.loading = false
    wordCard.found = !!d.found
    if (d.found) {
      wordCard.word = d.word
      wordCard.phonetic = d.phonetic
      wordCard.translation = d.translation
    }
  } catch (e) {
    if (my !== seq) return
    wordCard.loading = false
    wordCard.error = e.isNetwork ? '后端不可达，查词失败' : e.message
  }
}

export function closeWordCard() {
  wordCard.visible = false
}
