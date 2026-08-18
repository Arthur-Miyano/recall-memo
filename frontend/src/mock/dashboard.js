// Mock：仪表盘数据
// 未来对应后端接口：GET /api/dashboard —— 背诵档案台聚合数据
//   日历热力 / 7 天趋势 / 各栈正确率 / 知识图谱 / 今日建议
// 设置面板另对应：GET/POST /api/settings/llm（密钥只回掩码）
export const dashboard = {
  headMeta: ['已覆盖 6 / 14 题 · 连续打卡 3 天', '数据截至 2026.08.13'],
  // 每日背诵记录：0~4 五个热度等级（l1~l4 对应 CSS 类）
  calendar: [0,1,0,2,3,1,0, 1,2,4,2,0,1,3, 0,1,3,2,4,1,0, 2,1,0,3,2,4,1],
  // 近 7 天答题趋势（次数），days 为 X 轴标签
  trend: { values: [2, 0, 3, 1, 4, 2, 3], days: ['四','五','六','日','一','二','三'], max: 5 },
  // 各技术栈正确率（0~100，渲染为 10 格像素条）
  accuracy: [
    { name: 'PYTHON', pct: 68 },
    { name: 'AGENT', pct: 86 },
    { name: 'VUE 3', pct: 41 },
  ],
  // 知识图谱小卡片（概览态）：每栈 掌握/薄弱/未背 计数 + 完成比例
  stackOv: [
    { key: 'python', label: 'PYTHON', done: 3, weak: 2, todo: 9, total: 14 },
    { key: 'agent',  label: 'AGENT',  done: 5, weak: 0, todo: 7, total: 12 },
    { key: 'vue3',   label: 'VUE 3',  done: 1, weak: 1, todo: 4, total: 6 },
  ],
  // 今日建议背诵
  suggestions: [
    { d: '9 天未练', t: 'Vue 3 响应式原理（Proxy vs defineProperty）', s: '41%' },
    { d: '背诵痕迹', t: 'GIL 与多线程性能', s: '74.5' },
    { d: '低分', t: '装饰器底层机制', s: '56.5' },
  ],
  // 模型与密钥配置
  settings: {
    providers: ['DEEPSEEK', 'KIMI', '智谱', '豆包'],
    providerOn: 0,
    model: 'deepseek-chat',
    keyPlaceholder: 'sk-…（仅保存到本地 .env）',
    keyStatus: '未配置',
    // 「从环境变量提取」演示结果
    envPulled: { name: 'DEEPSEEK_API_KEY（环境变量）', masked: 'sk-••••81d7' },
  },
  // API 消耗（LLM 用量）：全量总计 + 近 30 天每日 + 按模型分组
  usage: {
    totals: { cost: 6.83, requests: 927, tokens: 86925716 },
    daily: mockUsageDaily(),
    models: [
      { model: 'deepseek-chat', provider: 'deepseek', cost: 6.83, requests: 927, tokens: 86925716 },
    ],
  },
}

// 近 30 天演示用量：少量几个峰值，其余近零
function mockUsageDaily() {
  const costs = [0, .04, 0, .05, .41, .28, 0, .27, .02, .03, 0, 0, 1.28, 1.69, .04, .07, .03, .28, 1.14, .11, 0, .37, .45, .13, .02, .39, 0, 0, .02, .05]
  return costs.map((cost, i) => {
    const d = new Date()
    d.setDate(d.getDate() - (29 - i))
    const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    return { date, cost, requests: Math.round(cost * 135), tokens: Math.round(cost * 1.27e7) }
  })
}
