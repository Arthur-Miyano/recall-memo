// composable：水墨螃蟹的拖动（pointer 事件 + 位置持久化）
// 职责：按住拖动到视口内任意位置（存 localStorage recall-crab-pos）；
//       位移 < 6px 视为点击（onTap），否则为拖动落地（onDrop）
// 钳制计算在 utils/crabGeometry.js
import { ref, onUnmounted } from 'vue'
import { clampCrabPos } from '../utils/crabGeometry'

export function useCrabDrag({ onTap, onDrop }) {
  // 螃蟹左上角坐标（fixed 定位），默认左上角；读取上次拖到的位置
  const pos = ref({ x: 28, y: 76 })
  try {
    const saved = JSON.parse(localStorage.getItem('recall-crab-pos'))
    if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) pos.value = saved
  } catch { /* 损坏数据忽略，用默认位置 */ }

  const dragging = ref(false)
  let grabOffset = { x: 0, y: 0 }   // 按下点相对螃蟹左上角的偏移
  let startClient = { x: 0, y: 0 }  // 按下时的指针坐标，用于计算位移区分点击/拖动
  let dragDist = 0

  function onPointerDown(e) {
    dragging.value = true
    dragDist = 0
    grabOffset = { x: e.clientX - pos.value.x, y: e.clientY - pos.value.y }
    startClient = { x: e.clientX, y: e.clientY }
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp, { once: true })
  }

  function onPointerMove(e) {
    dragDist = Math.hypot(e.clientX - startClient.x, e.clientY - startClient.y)
    // 跟随指针，钳制在视口内（螃蟹 84×84）
    pos.value = clampCrabPos(e.clientX - grabOffset.x, e.clientY - grabOffset.y, window.innerWidth, window.innerHeight)
  }

  function onPointerUp() {
    window.removeEventListener('pointermove', onPointerMove)
    dragging.value = false
    localStorage.setItem('recall-crab-pos', JSON.stringify(pos.value))
    if (dragDist < 6) onTap()   // 几乎没位移 = 点击
    else onDrop()               // 拖动落地，吐一串泡泡
  }

  onUnmounted(() => window.removeEventListener('pointermove', onPointerMove))

  return { pos, dragging, onPointerDown, onPointerMove, onPointerUp }
}
