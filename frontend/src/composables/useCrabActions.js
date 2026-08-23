// composable：助理动作卡片（确认后执行题库写操作）
// 职责：后端只提议不执行（action 为 LLM 提议的删/改/迁移）；用户点「确认执行」后
//       由这里直接调题库接口（DELETE 逐个 / PATCH / POST migrate），结果追加为新消息；
//       pending → done / cancelled；执行失败保持 pending 可重试
// 参数：messages（结果消息追加）、scrollBottom（结束后滚底）
import { request } from '../api'

// 卡片头部的动作类型标注
const ACTION_LABELS = { delete_questions: '删除题目', edit_question: '修改题目', migrate_questions: '迁移题目' }

export function useCrabActions({ messages, scrollBottom }) {
  async function runAction(m) {
    if (m.actionState !== 'pending' || m.actionRunning) return
    const a = m.action
    m.actionRunning = true
    try {
      let result = ''
      if (a.type === 'delete_questions') {
        let deleted = 0
        for (const id of a.question_ids) {
          try { await request(`/api/bank/questions/${id}`, { method: 'DELETE' }); deleted++ }
          catch (e) { console.warn(`[crab] 删除题目 #${id} 失败：`, e.message) }
        }
        result = `已删除 ${deleted} 道题`
          + (deleted < a.question_ids.length ? `（${a.question_ids.length - deleted} 道删除失败）` : '')
      } else if (a.type === 'edit_question') {
        await request(`/api/bank/questions/${a.question_ids[0]}`, { method: 'PATCH', body: a.changes })
        result = `已更新题目 #${a.question_ids[0]}（${Object.keys(a.changes).join('、')}）`
      } else if (a.type === 'migrate_questions') {
        const d = await request('/api/bank/questions/migrate', {
          method: 'POST', body: { question_ids: a.question_ids, to_stack: a.to_stack },
        })
        result = `已把 ${d.moved} 道题迁移到「${d.to_stack}」`
          + (d.missing && d.missing.length ? `（${d.missing.length} 道不存在被跳过）` : '')
      } else {
        throw new Error(`未知动作类型：${a.type}`)
      }
      m.actionState = 'done'
      messages.value.push({ who: '记忆助手', text: `${result}。题库已更新，到「题库」页可看到最新状态。` })
    } catch (e) {
      console.warn('[crab] 动作执行失败：', e.message)
      // 保持 pending 允许重试
      messages.value.push({ who: '记忆助手', text: `执行失败：${e.message}。可以点卡片上的「确认执行」重试，或取消。` })
    } finally {
      m.actionRunning = false
      scrollBottom()
    }
  }

  function cancelAction(m) {
    if (m.actionState !== 'pending' || m.actionRunning) return
    m.actionState = 'cancelled'
  }

  function actionLabel(a) { return ACTION_LABELS[a.type] || '题库操作' }

  return { runAction, cancelAction, actionLabel }
}
