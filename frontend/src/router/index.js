import { createRouter, createWebHistory } from 'vue-router'
import HomeDrawers from '../views/HomeDrawers.vue'
import MemorizeFlow from '../views/MemorizeFlow.vue'
import BankOverview from '../views/BankOverview.vue'
import InterviewRoom from '../views/InterviewRoom.vue'
import ReviewReport from '../views/ReviewReport.vue'
import DashboardView from '../views/DashboardView.vue'
import NotesView from '../views/NotesView.vue'

// 7 屏路由；顶部导航只显示未隐藏项，编号按可见顺序连号
// navHide：记忆训练/面试答题只从首页抽屉进入，不出现在顶部导航（防误触直达开始答题）
const routes = [
  { path: '/', name: 'home', component: HomeDrawers, meta: { nav: '01 首页' } },
  { path: '/memorize', name: 'memorize', component: MemorizeFlow, meta: { nav: '记忆训练', navHide: true } },
  { path: '/bank', name: 'bank', component: BankOverview, meta: { nav: '02 题库总览' } },
  { path: '/interview', name: 'interview', component: InterviewRoom, meta: { nav: '面试答题', navHide: true } },
  { path: '/review', name: 'review', component: ReviewReport, meta: { nav: '03 复盘报告' } },
  { path: '/dashboard', name: 'dashboard', component: DashboardView, meta: { nav: '04 仪表盘' } },
  { path: '/notes', name: 'notes', component: NotesView, meta: { nav: '05 笔记' } },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
