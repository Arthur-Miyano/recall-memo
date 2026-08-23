// composable：仪表盘卡片数据加载（首屏 + 录入成功后刷新共用）
// 职责：并行拉 5 个统计接口 → 组装 db 卡片数据；任一失败回退 mock 骨架并 console.warn
// 图表坐标/计数等纯映射在 utils/dashboardMapping.js
import { ref } from 'vue'
import { dashboard as mockDb } from '../mock/dashboard'
import { getStatsOverview, getStatsDaily, getBankOverview, getLlmUsage } from '../api'
import {
  WEEKDAYS_CN, mockCalItems, countStreak, buildStackOverview, buildSuggestions,
} from '../utils/dashboardMapping'

export function useDashboardData() {
  // 整体数据：先渲染 mock 骨架，真实数据到位后逐块替换
  // 日历字段统一为 InkCalendar 的 items 结构 [{date, total_count}]
  const db = ref({ ...mockDb, calendar: mockCalItems(mockDb.calendar) })

  async function loadDashboard() {
    try {
      const [ov, daily90, daily7, bank, usage] = await Promise.all([
        getStatsOverview(), getStatsDaily(90), getStatsDaily(7), getBankOverview(), getLlmUsage(30),
      ])
      db.value = {
        headMeta: [
          `已覆盖 ${ov.covered} / ${ov.total_questions} 题 · 连续打卡 ${countStreak(daily7.items)} 天`,
          `数据截至 ${new Date().toLocaleDateString('zh-CN')}`,
        ],
        // 月历热力：一次拉 90 天，InkCalendar 前端按月切换；等级逻辑在组件内（0~4 级）
        calendar: daily90.items,
        trend: {
          values: daily7.items.map(d => d.total_count),
          days: daily7.items.map(d => WEEKDAYS_CN[new Date(d.date + 'T00:00:00').getDay()]),
          max: Math.max(...daily7.items.map(d => d.total_count), 1),
        },
        accuracy: Object.entries(ov.per_stack).map(([name, s]) => ({
          name: name.toUpperCase(),
          pct: s.pass_rate == null ? 0 : Math.round(s.pass_rate * 100),
        })),
        stackOv: buildStackOverview(bank),
        suggestions: buildSuggestions(bank),
        usage,                              // API 消耗：totals + 30 天 daily + models
        settings: mockDb.settings, // 设置面板自行请求真实接口，这里仅占位
      }
    } catch (e) {
      console.warn('[dashboard] 统计数据获取失败，回退 mock 数据：', e.message)
    }
  }

  return { db, loadDashboard }
}
