import test from 'node:test'
import assert from 'node:assert/strict'

import { nodeKey, isCollapsed, toggleCollapsed } from './treeState.js'

test('节点路径转 key', () => {
  assert.equal(nodeKey([]), '')
  assert.equal(nodeKey([0]), '0')
  assert.equal(nodeKey([2, 1, 0]), '2/1/0')
})

test('默认全部展开：不在集合里即未折叠', () => {
  assert.equal(isCollapsed(new Set(), '0'), false)
})

test('切换折叠：收起再展开，原集合不被改动', () => {
  const s0 = new Set()
  const s1 = toggleCollapsed(s0, '0/1')
  assert.equal(isCollapsed(s1, '0/1'), true)
  assert.equal(isCollapsed(s0, '0/1'), false) // 不可变：返回新集合
  const s2 = toggleCollapsed(s1, '0/1')
  assert.equal(isCollapsed(s2, '0/1'), false)
})
