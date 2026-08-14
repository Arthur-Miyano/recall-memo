// Mock：面试答题数据
// 未来对应后端接口：
//   GET  /api/interview/session/current —— 当前场次信息 + 当前题（含追问进度）
//   POST /api/interview/answers         —— 提交作答（面试模式不即时反馈）
export const interviewSession = {
  topLeft: 'INTERVIEW — 混合场 4 题',
  progressTag: '第 2 / 4 题',
  // 倒计时：totalSec 为本题限时，leftSec 为进入页面时的剩余秒数
  totalSec: 120,
  leftSec: 107, // 1:47
  question: '“我们知道 CPython 里有个 GIL。那在实际项目里，它对多线程程序的性能到底意味着什么？你会怎么绕开它？”',
  followTag: '追问 1 / 2',
  placeholder: '开始输入即视为开始作答。用自己的话讲，别背。',
  note: '// 面试模式下不反馈对错，终局统一复盘',
}
