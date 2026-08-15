// 仪表盘放大视图 & 录入题库的业务接口封装
// 传输层（request/requestForm/错误处理/离线标记）统一复用 api/index.js，本文件只保留业务函数
// 用法约定同 index.js：try { 真实数据 } catch { console.warn + 空态/回退 } —— 页面永远不白屏
import { request, requestForm } from './index'

/* ---------- 仪表盘放大视图 ---------- */
// 近 N 天逐日答题明细（只含答题日）：每日背诵记录放大视图
export const getStatsDailyDetail = (days = 30) => request(`/api/stats/daily-detail?days=${days}`)
// 逐题明细（题干/答案/最近得分/次数/状态/近 5 次得分）：正确率放大表格 + 图谱节点详情
export const getStatsPerQuestion = () => request('/api/stats/per-question')
// 30 天趋势（成功/失败分开画）：近 7 天趋势放大视图
export const getStatsDaily = (days = 30) => request(`/api/stats/daily?days=${days}`)
// 知识图谱节点状态：图谱放大视图
export const getBankOverview = () => request('/api/bank/overview')
// 待补答队列：今日建议放大视图
export const getRetryQueue = () => request('/api/sessions/retry-queue')
// 「问问助手怎么安排」：quick=plan 快捷指令
export const postAssistantPlan = () =>
  request('/api/assistant/chat', { method: 'POST', body: { quick: 'plan' } })

/* ---------- 录入题库 ---------- */
// {text, dedupe} → {imported, skipped, enriched, errors}
export const postBankImport = (text, dedupe = true) =>
  request('/api/bank/import', { method: 'POST', body: { text, dedupe } })
// 文件上传（PDF 由后端 pypdf 提取，md/txt/json 读文本）→ 同上返回结构
export const postBankImportFile = (file, dedupe = true) => {
  const form = new FormData()
  form.append('file', file)
  form.append('dedupe', dedupe ? 'true' : 'false')
  return requestForm('/api/bank/import-file', form)
}
