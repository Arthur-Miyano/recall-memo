import { createRouter, createWebHistory } from 'vue-router'
import HomeDrawers from '../views/HomeDrawers.vue'
import MemorizeFlow from '../views/MemorizeFlow.vue'
import BankOverview from '../views/BankOverview.vue'
import InterviewRoom from '../views/InterviewRoom.vue'
import ReviewReport from '../views/ReviewReport.vue'
import DashboardView from '../views/DashboardView.vue'

// 6 屏路由，与原型的 proto-nav 顺序一致
const routes = [
  { path: '/', name: 'home', component: HomeDrawers, meta: { nav: '01 首页' } },
  { path: '/memorize', name: 'memorize', component: MemorizeFlow, meta: { nav: '02 记忆训练' } },
  { path: '/bank', name: 'bank', component: BankOverview, meta: { nav: '03 题库总览' } },
  { path: '/interview', name: 'interview', component: InterviewRoom, meta: { nav: '04 面试答题' } },
  { path: '/review', name: 'review', component: ReviewReport, meta: { nav: '05 复盘报告' } },
  { path: '/dashboard', name: 'dashboard', component: DashboardView, meta: { nav: '06 仪表盘' } },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
