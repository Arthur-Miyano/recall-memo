// 跨视图会话状态：面试结束后把 session_id 带给复盘页
import { defineStore } from 'pinia'

export const useSessionStore = defineStore('session', {
  state: () => ({
    // 最近一次完成（进入终局复盘）的面试会话 id
    lastReviewSessionId: null,
  }),
})
