import test from 'node:test'
import assert from 'node:assert/strict'

import {
  fmtDate, mockCalItems, buildStrip28, countStreak, kgLabel,
  buildStackOverview, buildSuggestions, makeBars, fmtInt, fmtBig,
  axisX, axisY, stepPath, sortPerQRows, defaultKgStack,
} from './dashboardMapping.js'

const NOW = new Date(2026, 7, 23) // 2026-08-23（本地时区，与 fmtDate 口径一致）

test('fmtDate 输出 YYYY-MM-DD 并补零', () => {
  assert.equal(fmtDate(new Date(2026, 0, 5)), '2026-01-05')
  assert.equal(fmtDate(NOW), '2026-08-23')
})

test('mockCalItems 把 28 个等级数字映射为最近 28 天（末位是今天）', () => {
  const items = mockCalItems(Array.from({ length: 28 }, (_, i) => i % 5), NOW)
  assert.equal(items.length, 28)
  assert.equal(items[27].date, '2026-08-23')
  assert.equal(items[0].date, '2026-07-27')
  assert.equal(items[27].total_count, 27 % 5)
})

test('buildStrip28：28 格、今天红框、等级封顶 4、按日期查计数', () => {
  const days = buildStrip28([{ date: '2026-08-23', total_count: 7 }], NOW)
  assert.equal(days.length, 28)
  assert.equal(days[27].isToday, true)
  assert.equal(days[0].isToday, false)
  assert.equal(days[27].level, 4)
  assert.equal(days[27].tip, '8月23日 · 7 题')
  assert.equal(days[26].level, 0) // 无记录日期补 0
})

test('countStreak 从今天往前数连续有答题的天数', () => {
  assert.equal(countStreak([{ total_count: 1 }, { total_count: 0 }, { total_count: 3 }, { total_count: 2 }]), 2)
  assert.equal(countStreak([{ total_count: 0 }]), 0)
  assert.equal(countStreak([]), 0)
})

test('kgLabel：>8 字截断；同知识点多题加圈号，超出 ⑳ 兜底 ·n', () => {
  assert.equal(kgLabel('列表', 1, 1), '列表')
  assert.equal(kgLabel('一个非常长的知识点名称', 1, 1), '一个非常长的知识…')
  assert.equal(kgLabel('列表', 2, 3), '列表 ②')
  assert.equal(kgLabel('列表', 21, 25), '列表 ·21')
})

test('buildStackOverview 按状态计数，total 缺省时用计数和', () => {
  const bank = {
    stacks: [{
      key: 'python', name: 'Python', total: 0,
      groups: [{ cells: [{ status: 'done' }, { status: 'weak' }, { status: 'todo' }, { status: 'done' }] }],
    }],
  }
  assert.deepEqual(buildStackOverview(bank), [
    { key: 'python', label: 'PYTHON', done: 2, weak: 1, todo: 1, total: 4 },
  ])
})

test('buildSuggestions：只取薄弱题，按分升序，最多 3 条', () => {
  const cell = (score, retry, tip) => ({ status: 'weak', score, retry, tip })
  const bank = {
    stacks: [{
      groups: [{
        name: 'g',
        cells: [
          cell(80, false, 't80 · x'), cell(40, true, 't40 · x'),
          cell(60, false, 't60 · x'), cell(20, false, 't20 · x'),
          { status: 'done', score: 10, tip: 'done · x' },
        ],
      }],
    }],
  }
  const s = buildSuggestions(bank)
  assert.equal(s.length, 3)
  assert.deepEqual(s.map(x => x.s), ['20', '40', '60'])
  assert.equal(s[1].d, '待补答') // retry 标记优先
  assert.equal(s[0].t, 't20')    // tip 取 · 前段
})

test('makeBars：空数组安全；柱高 ∝ 数值且基线对齐', () => {
  assert.deepEqual(makeBars([], 'cost', 560, 120, 28, 10), { bars: [], max: 0 })
  const { bars, max } = makeBars([
    { date: '2026-08-01', cost: 1 }, { date: '2026-08-02', cost: 2 },
  ], 'cost', 560, 120, 28, 10)
  assert.equal(max, 2)
  assert.equal(bars[1].h, 64)              // 最大值顶满绘图区（H - 2*pad）
  assert.equal(bars[0].h, 32)
  assert.equal(bars[0].y + bars[0].h, 92)  // y + h = H - pad（同一基线）
})

test('数值格式化：千分位与 k/M 缩写', () => {
  assert.equal(fmtInt(1234567), '1,234,567')
  assert.equal(fmtInt(null), '0')
  assert.equal(fmtBig(2500000), '2.5M')
  assert.equal(fmtBig(1500), '1.5k')
  assert.equal(fmtBig(12), '12')
})

test('阶梯折线坐标：slots 决定水平间距，值决定垂直位置', () => {
  assert.equal(axisX(0, 560, 28, 6), 28)
  assert.equal(axisX(6, 560, 28, 6), 532)
  assert.equal(axisY(0, 5, 160, 28), 132)
  assert.equal(axisY(5, 5, 160, 28), 28)
  assert.equal(stepPath([1, 3], 5, 560, 160, 28, 6), 'M 28 111.2 H 112 V 69.6')
  assert.equal(stepPath([], 5, 560, 160, 28, 6), '')
})

test('sortPerQRows：按技术栈分组，同栈内 薄弱 → 掌握 → 未背', () => {
  const rows = sortPerQRows([
    { tech_stack: 'python', status: 'todo' },
    { tech_stack: 'go', status: 'done' },
    { tech_stack: 'python', status: 'weak' },
    { tech_stack: 'python', status: 'done' },
  ])
  assert.deepEqual(rows.map(r => `${r.tech_stack}:${r.status}`), [
    'go:done', 'python:weak', 'python:done', 'python:todo',
  ])
})

test('defaultKgStack 选掌握数最少的栈，空数据兜底空串', () => {
  assert.equal(defaultKgStack({ stacks: [{ key: 'a', done: 3 }, { key: 'b', done: 1 }, { key: 'c', done: 2 }] }), 'b')
  assert.equal(defaultKgStack({ stacks: [] }), '')
  assert.equal(defaultKgStack(null), '')
})
