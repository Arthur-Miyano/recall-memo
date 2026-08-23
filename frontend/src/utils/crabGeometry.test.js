import test from 'node:test'
import assert from 'node:assert/strict'

import { clampCrabPos, clampPanelSize, panelOffset } from './crabGeometry.js'

test('螃蟹位置钳制在视口内（84×84）', () => {
  assert.deepEqual(clampCrabPos(-50, 1000, 800, 600), { x: 0, y: 516 })
  assert.deepEqual(clampCrabPos(28, 76, 800, 600), { x: 28, y: 76 })
  assert.deepEqual(clampCrabPos(790, 590, 800, 600), { x: 716, y: 516 })
})

test('面板尺寸钳制：下限 320×360，上限 0.9 屏宽 / 0.85 屏高', () => {
  assert.deepEqual(clampPanelSize(100, 100, 800, 600), { w: 320, h: 360 })
  assert.deepEqual(clampPanelSize(2000, 2000, 800, 600), { w: 720, h: 510 })
  assert.deepEqual(clampPanelSize(380, 460, 800, 600), { w: 380, h: 460 })
})

test('面板跟随螃蟹：上半屏向下开，紧贴螃蟹底部', () => {
  assert.deepEqual(panelOffset({ x: 28, y: 76 }, { w: 380, h: 460 }, 1280, 800), { left: 28, top: 168 })
})

test('面板跟随螃蟹：下半屏向上开；右/下边缘钳制回视口', () => {
  // y=700 + 92 + 460 超出 800 → 向上开：top = 700 - 460 - 8
  assert.deepEqual(panelOffset({ x: 28, y: 700 }, { w: 380, h: 460 }, 1280, 800), { left: 28, top: 232 })
  // 螃蟹贴右边缘：left 钳制到 vw - w - 8
  assert.equal(panelOffset({ x: 1200, y: 100 }, { w: 380, h: 460 }, 1280, 800).left, 892)
  // 向下开但放不到底：top 钳制到 vh - h - 8（245+92+460=797 < 800 仍向下开，337 收回到 332）
  assert.equal(panelOffset({ x: 28, y: 245 }, { w: 380, h: 460 }, 1280, 800).top, 332)
})
