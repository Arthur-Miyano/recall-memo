// 水墨螃蟹与对话面板的纯几何计算（视口钳制）
// 从 components/InkCrab.vue 抽出：无 DOM/Vue 依赖，便于 node --test 直测
// 螃蟹固定 84×84（SVG viewBox 与 .crab 尺寸一致）；面板最小 320×360

export const CRAB_SIZE = 84
export const PANEL_MIN = { w: 320, h: 360 }

// 螃蟹位置钳制在视口内
export function clampCrabPos(x, y, vw, vh, size = CRAB_SIZE) {
  return {
    x: Math.min(Math.max(x, 0), vw - size),
    y: Math.min(Math.max(y, 0), vh - size),
  }
}

// 面板尺寸钳制：下限 PANEL_MIN，上限 0.9 屏宽 / 0.85 屏高
export function clampPanelSize(w, h, vw, vh, min = PANEL_MIN) {
  const maxW = Math.round(vw * 0.9)
  const maxH = Math.round(vh * 0.85)
  return {
    w: Math.min(Math.max(w, min.w), maxW),
    h: Math.min(Math.max(h, min.h), maxH),
  }
}

// 面板位置：水平对齐螃蟹并钳制在视口内；螃蟹在下半屏时面板向上开，避免被裁掉
export function panelOffset(pos, size, vw, vh) {
  const left = Math.min(Math.max(pos.x, 8), Math.max(8, vw - size.w - 8))
  const openBelow = pos.y + 92 + size.h < vh
  const top = openBelow
    ? Math.min(pos.y + 92, Math.max(8, vh - size.h - 8))
    : Math.max(8, pos.y - size.h - 8)
  return { left, top }
}
