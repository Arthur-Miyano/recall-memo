// Mock：题库总览数据
// 未来对应后端接口：
//   GET  /api/bank/overview        —— 技术栈 → 知识点分组 → 题目背诵状态格
//   POST /api/bank/focus           —— 圈选/取消「重点背诵」分组
export const bankOverview = {
  done: 6,
  total: 14,
  // status: done=已掌握(墨块) / weak=薄弱·待补答(红斜纹) / todo=未背(空白)
  stacks: [
    {
      name: 'Python', total: 6, done: 2,
      groups: [
        {
          name: '并发编程', starred: true,
          cells: [
            { tip: 'GIL 与多线程性能 · 74.5 分 · 背诵痕迹', status: 'weak' },
            { tip: '协程与 asyncio · 未背', status: 'todo' },
          ],
        },
        {
          name: 'Web / FastAPI', starred: false,
          cells: [
            { tip: 'FastAPI 依赖注入 · 未背', status: 'todo' },
            { tip: 'Pydantic 数据校验 · 未背', status: 'todo' },
          ],
        },
        {
          name: '语言基础', starred: false,
          cells: [
            { tip: '装饰器底层机制 · 56.5 分 · 待补答', status: 'weak' },
            { tip: '生成器与迭代器 · 85 分', status: 'done' },
          ],
        },
      ],
    },
    {
      name: 'Agent', total: 4, done: 3,
      groups: [
        {
          name: '推理范式', starred: false,
          cells: [
            { tip: 'ReAct 模式 · 82 分', status: 'done' },
            { tip: 'Plan-and-Execute · 78 分', status: 'done' },
          ],
        },
        {
          name: '工具调用', starred: false,
          cells: [
            { tip: 'Function Calling 原理 · 88 分', status: 'done' },
            { tip: 'MCP 协议 · 未背', status: 'todo' },
          ],
        },
      ],
    },
    {
      name: 'Vue 3', total: 4, done: 1,
      groups: [
        {
          name: '响应式系统', starred: false,
          cells: [
            { tip: 'Proxy vs defineProperty · 41% · 9 天未练', status: 'weak' },
            { tip: 'ref vs reactive · 未背', status: 'todo' },
          ],
        },
        {
          name: '状态管理', starred: false,
          cells: [
            { tip: 'Pinia 核心概念 · 80 分', status: 'done' },
            { tip: 'Pinia vs Vuex · 未背', status: 'todo' },
          ],
        },
      ],
    },
  ],
}
