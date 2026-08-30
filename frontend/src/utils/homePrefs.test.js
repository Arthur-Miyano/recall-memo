// homePrefs 纯函数测试：选项解析与题量恢复（存储读写不在 node 环境测）
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { resolveStackIndex, resolveStackIndices, resolveCount } from './homePrefs.js'

test('resolveStackIndex: 命中保存值返回对应下标', () => {
  const options = [{ value: 'agent', label: 'Agent' }, { value: 'python', label: 'Python' }]
  assert.equal(resolveStackIndex(options, 'python', 0), 1)
})

test('resolveStackIndex: 字符串数组选项也能匹配', () => {
  assert.equal(resolveStackIndex(['a', 'b', 'c'], 'c', 0), 2)
})

test('resolveStackIndex: 找不到（栈已删除）回退默认', () => {
  const options = [{ value: 'agent', label: 'Agent' }]
  assert.equal(resolveStackIndex(options, 'vue3', 0), 0)
})

test('resolveStackIndices: 多值数组返回下标集合', () => {
  const options = [{ value: 'agent', label: 'Agent' }, { value: 'python', label: 'Python' }, { value: 'mixed', label: '混合' }]
  assert.deepEqual(resolveStackIndices(options, ['python', 'agent'], 2), new Set([0, 1]))
})

test('resolveStackIndices: 兼容旧单值字符串', () => {
  const options = [{ value: 'agent', label: 'Agent' }, { value: 'python', label: 'Python' }]
  assert.deepEqual(resolveStackIndices(options, 'python', 0), new Set([1]))
})

test('resolveStackIndices: 全部找不到或为空时回退默认下标', () => {
  const options = [{ value: 'agent', label: 'Agent' }, { value: 'mixed', label: '混合' }]
  assert.deepEqual(resolveStackIndices(options, ['vue3'], 1), new Set([1]))
  assert.deepEqual(resolveStackIndices(options, [], 1), new Set([1]))
  assert.deepEqual(resolveStackIndices(options, undefined, 0), new Set([0]))
})

test('resolveCount: 命中胶囊返回胶囊下标', () => {
  assert.deepEqual(resolveCount(5, [3, 5, 7], 0), { index: 1 })
})

test('resolveCount: 不在胶囊里的合法数字走自由输入', () => {
  assert.deepEqual(resolveCount(12, [3, 5, 7], 0), { custom: 12 })
})

test('resolveCount: 越界或非法值回退默认胶囊', () => {
  assert.deepEqual(resolveCount(99, [3, 5, 7], 0), { index: 0 })
  assert.deepEqual(resolveCount('abc', [3, 5, 7], 0), { index: 0 })
  assert.deepEqual(resolveCount(undefined, [3, 5, 7], 1), { index: 1 })
})
