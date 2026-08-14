// Mock：记忆训练流程数据
// 未来对应后端接口：
//   GET  /api/memorize/session        —— 本轮展示的题目列表（题干 + 标准答案）
//   GET  /api/memorize/session/quiz   —— 打乱后的考核变体题干 + 关键词提示
//   POST /api/memorize/answers        —— 提交考核作答，返回评分 AGENT 的即时反馈
export const memorizeSession = {
  topLeft: 'MEMORIZE — PYTHON · 本轮 3 题',
  topRight: 'MEMORIZE_SHOW — 记忆中',
  // 阶段一：展示记忆
  questions: [
    {
      no: '题 1 / 3',
      title: 'Python 的 GIL 是什么？对多线程有何影响？',
      retry: true, // 「待补答」红标
      answer: 'GIL（全局解释器锁）是 CPython 中的互斥锁，保证同一时刻只有一个线程执行字节码。它存在的根本原因是引用计数的内存管理不是线程安全的。CPU 密集型任务无法利用多核，应改用多进程；I/O 密集型任务中线程等待时会释放 GIL，仍有并发收益。',
    },
    {
      no: '题 2 / 3',
      title: '装饰器的底层原理是什么？',
      retry: false,
      answer: '装饰器本质是"接收函数、返回函数"的高阶函数，@语法糖等价于 func = decorator(func)。通过闭包保存原函数引用，用 functools.wraps 保留原函数元信息。带参装饰器需要再嵌套一层。',
    },
    {
      no: '题 3 / 3',
      title: '生成器与迭代器的区别？',
      retry: false,
      answer: '迭代器是实现 __iter__ 和 __next__ 的对象；生成器是特殊的迭代器，用 yield 惰性产生值，函数调用时返回生成器对象而不立即执行，每次 next 从上次 yield 处继续。生成器表达式比列表推导更省内存。',
    },
  ],
  // 阶段二：打乱考核（变体题干 + 关键词提示）
  quiz: {
    question: '"聊一下装饰器吧——它底下到底是怎么工作的？为什么加了 @ 就能增强一个函数？"',
    followTag: '考核 1 / 3 · 已打乱',
    keywords: ['高阶函数', '闭包', 'functools.wraps', '语法糖'],
    placeholder: '用自己的话讲，别背。',
    // 提交后的即时反馈
    feedback: {
      no: 'FEEDBACK — 评分 AGENT',
      title: '本题反馈',
      score: '67.1',
      dims: [
        { label: '准确性 50%', value: 72, seal: false },
        { label: '逻辑 30%', value: 80, seal: false },
        { label: '自然度 20%', value: 3, seal: true },
      ],
      comment: '点评：核心机制讲到了高阶函数和闭包，但与标准答案逐字重合率 48%，有明显背诵痕迹；functools.wraps 的作用未提及。建议合上讲义，用"装饰器就像给函数穿外套"这类自己的比喻重述一遍。',
      yourAnswer: '装饰器是接收函数返回函数的高阶函数，通过闭包保存原函数引用……',
      stdAnswer: '装饰器本质是"接收函数、返回函数"的高阶函数，@语法糖等价于 func = decorator(func)……',
    },
  },
}
