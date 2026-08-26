// 记忆树提取的业务接口封装
// 传输层（request/错误处理/离线标记）统一复用 api/index.js，本文件只保留业务函数
// 用法约定同 index.js：try { 真实数据 } catch { console.warn + 空态 } —— 页面永远不白屏
import { request } from './index'

// 按技术栈分组的覆盖统计 → {stacks: [{tech_stack, total, with_tree, missing}], total: {...}}
export const getMemtreeStatus = () => request('/api/memtree/status')
// 创建生成任务：{stack?, regenerate?, questionIds?} → {job_id, status}；范围内无题时 400
export const postMemtreeJob = ({ stack = '', regenerate = false } = {}) =>
  request('/api/memtree/jobs', {
    method: 'POST',
    body: { stack: stack || undefined, regenerate },
  })
// 任务进度：{status, stage, stage_done, stage_total, result?}
export const getMemtreeJob = (id) => request(`/api/memtree/jobs/${id}`)
// 最近一次任务：打开面板时调用，还在跑就重新挂上轮询
export const getMemtreeJobLatest = () => request('/api/memtree/jobs/latest')
