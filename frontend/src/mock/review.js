// Mock：终局复盘报告数据
// 未来对应后端接口：GET /api/review/latest —— 最近一次面试场次的复盘报告
//   kind: question=单题复盘 / analysis=薄弱点分析 / followup=错题去向
export const reviewReport = {
  fileNo: 'INTERVIEW REPORT — FILE №20260813-02',
  title: '终局复盘报告',
  meta: ['场次：混合 4 题 · 用时 14:32', '2026.08.13 — 面试官 AGENT / 评分 AGENT 联署'],
  papers: [
    {
      kind: 'question',
      no: 'Q1 — PYTHON',
      title: 'GIL 与多线程性能',
      score: '74.5',
      stamp: '背诵痕迹', // 背诵痕迹印章
      dims: [
        { label: '准确性 50%', value: 95, seal: false },
        { label: '逻辑 30%', value: 90, seal: false },
        { label: '自然度 20%', value: 0, seal: true },
      ],
      yourAnswer: 'GIL 就是全局解释器锁，它是 CPython 解释器中的一个互斥锁，确保同一时刻只有一个线程执行 Python 字节码，从而简化了内存管理，但限制了多线程在多核 CPU 上的并行能力……',
      stdAnswer: 'GIL 是 CPython 的互斥锁，源于引用计数的线程安全问题。CPU 密集型任务无法真正并行，应使用多进程；I/O 密集型任务线程会在等待时释放 GIL，仍有并发收益……',
      misses: [
        '遗漏：GIL 存在的根本原因（引用计数线程安全）',
        '遗漏：绕开方案（multiprocessing / C 扩展释放 GIL）',
      ],
    },
    {
      kind: 'question',
      no: 'Q2 — AGENT · 追问链 1/2',
      title: 'ReAct 模式的推理循环',
      score: '82.0',
      stamp: null,
      dims: null,
      yourAnswer: 'ReAct 就是让模型一边想一边做：先 Reasoning 出下一步计划，再 Action 调工具，拿到观察结果后继续推理，直到任务完成……',
      stdAnswer: 'ReAct 交替进行推理（Thought）与行动（Action），每轮行动后观察（Observation）环境反馈并纳入上下文，形成闭环……',
      misses: null,
    },
    {
      kind: 'analysis',
      no: 'ANALYSIS — 智能助理 AGENT',
      title: '薄弱点分析',
      weakPoints: [
        '并发专题：GIL 考点答得出定义、讲不出工程取舍，建议结合多进程方案再背一轮',
        '表达自然度两场偏低，逐字复述标准答案的习惯需要纠正',
        'Agent 方向掌握最好，可降低该方向抽题权重',
        'Vue 3 已 9 天未出现，存在遗忘风险',
      ],
    },
    {
      kind: 'followup',
      no: 'FOLLOW-UP — 后续安排',
      title: '答错题目去向',
      retryQuestions: ['Q1 GIL 与多线程性能', 'Q4 装饰器底层机制'],
      note: '// 已自动加入「记忆训练」待补答队列，复习巩固在那里完成',
      cta: '去记忆训练 →',
    },
  ],
}
