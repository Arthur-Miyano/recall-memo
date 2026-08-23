// composable：对话面板尺寸（右下角自定义手柄拖动调整）
// 职责：pointer capture 拖动调宽高（与螃蟹拖动互不干扰）；尺寸存 localStorage 下次打开恢复。
//       panelSize 是唯一尺寸数据源：手柄拖动直接写 panelSize，不经 ResizeObserver——
//       原生 resize 手柄太小难抓，且 content-box/border-box 口径差曾导致"松手慢慢缩回"的反馈环
// 钳制计算在 utils/crabGeometry.js
import { ref } from 'vue'
import { clampPanelSize } from '../utils/crabGeometry'

export function useChatResize() {
  const panelSize = ref({ w: 380, h: 460 })
  try {
    const saved = JSON.parse(localStorage.getItem('recall-chat-size'))
    if (saved && Number.isFinite(saved.w) && Number.isFinite(saved.h)) panelSize.value = saved
  } catch { /* 损坏数据忽略，用默认尺寸 */ }

  // 手柄拖动：pointerdown 记起点尺寸，move 钳制范围写入，up 持久化
  let gripDrag = null   // { x, y, w, h } 拖动起点
  function onGripDown(e) {
    e.preventDefault()
    e.target.setPointerCapture(e.pointerId)   // 捕获后续 move/up，拖出手柄也不丢
    gripDrag = { x: e.clientX, y: e.clientY, w: panelSize.value.w, h: panelSize.value.h }
  }
  function onGripMove(e) {
    if (!gripDrag) return
    panelSize.value = clampPanelSize(
      gripDrag.w + e.clientX - gripDrag.x,
      gripDrag.h + e.clientY - gripDrag.y,
      window.innerWidth, window.innerHeight,
    )
  }
  function onGripUp() {
    if (!gripDrag) return
    gripDrag = null
    localStorage.setItem('recall-chat-size', JSON.stringify(panelSize.value))
  }

  return { panelSize, onGripDown, onGripMove, onGripUp }
}
