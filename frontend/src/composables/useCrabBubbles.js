// composable：水墨螃蟹吐泡泡
// 职责：bubbles 数组渲染墨线圈（bubbleUp 上升消散）；定时器每 4.5s 吐一个，burst() 连吐三个
import { ref, onMounted, onUnmounted } from 'vue'

export function useCrabBubbles() {
  // bubbles：{ id, size, ox(嘴部水平位置), dx(上升时水平漂移), dur }，动画结束后移除
  const bubbles = ref([])
  let bubbleSeq = 0
  let bubbleTimer = null

  function spawnBubble(big) {
    const id = ++bubbleSeq
    bubbles.value.push({
      id,
      size: big ? 6 + Math.random() * 8 : 3 + Math.random() * 5,
      ox: 32 + Math.random() * 20,
      dx: (Math.random() * 28 - 14).toFixed(0) + 'px',
      dur: (1.8 + Math.random() * 1.2).toFixed(2) + 's',
    })
    setTimeout(() => { bubbles.value = bubbles.value.filter(b => b.id !== id) }, 3200)
  }

  // 连吐三个大泡泡（拖动落地、收到答复时调用）
  function burst() { for (let i = 0; i < 3; i++) setTimeout(() => spawnBubble(true), i * 160) }

  onMounted(() => { bubbleTimer = setInterval(() => spawnBubble(false), 4500) })
  onUnmounted(() => clearInterval(bubbleTimer))

  return { bubbles, burst }
}
