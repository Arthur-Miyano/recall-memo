// Mock：首页模式抽屉数据
// 未来对应后端接口：GET /api/home/summary —— 返回三种模式的统计与可选配置
export const homeSummary = {
  date: '2026.08.13 — THU',
  // 标题下的一行统计摘要
  sub: '// 题库 14 题 · 已覆盖 6 题 · 近 7 天答题 9 次',
  drawers: [
    {
      idx: 'NO.01', name: '记忆训练', hint: 'MEMORIZE',
      stats: [
        { k: '未背题数', v: '8', small: ' / 14' },
        { k: '待补答', v: '2', small: ' 题', seal: true },
        { k: '上次训练', v: '2', small: ' 天前' },
        { k: '新题优先', v: 'ON' },
      ],
      // 可选项组：label + 单选胶囊（seal 表示印章红高亮组）
      optGroups: [
        { label: '题量', options: ['3 题', '5 题', '7 题'], on: 0, seal: false },
      ],
      cta: '开始记忆 →',
      note: '面试答错的题会进入待补答队列，在这里优先重背',
    },
    {
      idx: 'NO.02', name: '面试模拟', hint: 'INTERVIEW',
      stats: [
        { k: '限时', v: '2:00' },
        { k: '历史场次', v: '4', small: ' 场' },
        { k: '平均得分', v: '72.4' },
      ],
      optGroups: [
        { label: '技术栈', options: ['PYTHON', 'AGENT', 'VUE 3', '混合'], on: 3, seal: true },
        { label: '题量', options: ['3 题', '4 题', '5 题'], on: 1, seal: false },
      ],
      cta: '进入面试 →',
      note: '全程无反馈，终局统一复盘',
    },
    {
      idx: 'NO.03', name: '回忆模式', hint: 'RECALL',
      stats: [
        { k: '今日到期', v: '5', small: ' 题' },
        { k: '最久未复习', v: '9', small: ' 天' },
        { k: '平均得分', v: '72.4' },
        { k: '调度', v: 'EBH', small: ' 曲线' },
      ],
      optGroups: [],
      cta: '开始复习 →',
      note: '只抽背过的题，按遗忘程度排序',
    },
  ],
}
