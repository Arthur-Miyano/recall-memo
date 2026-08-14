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
  // 知识图谱：根节点（技术栈）+ 子节点（知识点，mastered/weak/todo）
  graph: {
    roots: [
      { x: 80,  y: 70,  label: 'PYTHON' },
      { x: 320, y: 70,  label: 'AGENT' },
      { x: 200, y: 260, label: 'VUE 3' },
    ],
    kids: {
      'PYTHON': [ {x:40,y:150,t:'GIL',s:'weak'}, {x:130,y:160,t:'装饰器',s:'weak'}, {x:70,y:210,t:'生成器',s:'todo'} ],
      'AGENT':  [ {x:300,y:150,t:'ReAct',s:'mastered'}, {x:360,y:180,t:'FunctionCall',s:'mastered'} ],
      'VUE 3':  [ {x:110,y:300,t:'响应式',s:'weak'}, {x:200,y:318,t:'Pinia',s:'todo'}, {x:290,y:300,t:'Diff',s:'todo'} ],
    },
  },
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
}
