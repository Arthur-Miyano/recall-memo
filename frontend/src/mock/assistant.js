// Mock：水墨螃蟹 · 记忆助手对话数据
// 未来对应后端接口：POST /api/assistant/chat
//   请求：{ message } —— 快捷提示词或自由输入
//   响应：{ thinking: string[], reply: string } —— 思考过程（Agent 调用链）+ 最终答复
export const assistant = {
  // 5 个快捷提示词
  quickPrompts: [
    { label: '今日总结', q: '总结我今天的背诵' },
    { label: '最近总结', q: '总结我最近的背诵' },
    { label: '全部总结', q: '总结我全部的背诵' },
    { label: '重点背诵建议', q: '我需要重点背诵哪些内容？' },
    { label: '制定背诵计划', q: '帮我规划一个背诵计划' },
  ],
  greeting: '你好，我守着你的背诵档案。点上面的快捷指令，或者直接问我。',
  // 演示用假回复：先展示"思考过程"（调用链），再给结论
  thinking: [
    '总控 Agent：解析意图 → 背诵情况查询',
    '智能助理 Agent：查询 records / daily_stats …',
    '智能助理 Agent：聚合 3 个技术栈正确率 …',
  ],
  reply: '你今天完成 1 场面试模拟（4 题，均分 72.4），其中 GIL 一题被判背诵痕迹。建议：先把「装饰器」补答掉，再开始 Vue 3 响应式——它已经 9 天没出现了。',
  replyDelayMs: 1200,
}
