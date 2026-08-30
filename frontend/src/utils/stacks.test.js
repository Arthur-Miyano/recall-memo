// stacks 纯函数测试：URL 多选参数解析与展示标签
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseStacksQuery, stackLabel } from './stacks.js'

test('parseStacksQuery: stacks 逗号分隔多值', () => {
  assert.deepEqual(parseStacksQuery({ stacks: 'python,agent' }), ['python', 'agent'])
})

test('parseStacksQuery: 兼容旧的单值 stack 参数', () => {
  assert.deepEqual(parseStacksQuery({ stack: 'python' }), ['python'])
})

test('parseStacksQuery: stacks 优先于 stack；空值返回空数组', () => {
  assert.deepEqual(parseStacksQuery({ stacks: 'agent', stack: 'python' }), ['agent'])
  assert.deepEqual(parseStacksQuery({ stacks: '' }), [])
  assert.deepEqual(parseStacksQuery({}), [])
})

test('parseStacksQuery: 过滤空段', () => {
  assert.deepEqual(parseStacksQuery({ stacks: 'python,,agent,' }), ['python', 'agent'])
})

test('stackLabel: 多栈大写拼接', () => {
  assert.equal(stackLabel(['python', 'agent']), 'PYTHON+AGENT')
})

test('stackLabel: 空或只含 mixed 时用回退值', () => {
  assert.equal(stackLabel(['mixed']), 'MIXED')
  assert.equal(stackLabel([], 'python'), 'PYTHON')
  assert.equal(stackLabel(null), 'MIXED')
})
