// 跨视图会话状态：面试结束后把 session_id 带给复盘页；记忆训练快照跨页面保持
import { defineStore } from 'pinia'

export const useSessionStore = defineStore('session', {
  state: () => ({
    // 最近一次完成（进入终局复盘）的面试会话 id
    lastReviewSessionId: null,
    // 记忆训练会话快照：开始训练后题目固定——切到别的页面再回来原样恢复；
    // 只有首页再次点「开始记忆」（带新 fresh token）才重开一轮抽题
    memorize: null,
  }),
})
