import { createRouter, createWebHashHistory } from 'vue-router'
import NProgress from 'nprogress'
import Dashboard from '@/views/Dashboard.vue'
import Import from '@/views/Import.vue'
import InvitePool from '@/views/InvitePool.vue'
import Register from '@/views/Register.vue'
import AutoLoop from '@/views/AutoLoop.vue'
import ProxyPool from '@/views/ProxyPool.vue'
import Pool from '@/views/Pool.vue'
import Registered from '@/views/Registered.vue'
import Runs from '@/views/Runs.vue'
import MailConfig from '@/views/MailConfig.vue'


NProgress.configure({ showSpinner: false, trickleSpeed: 120, minimum: 0.15 })

const routes = [
  {
    path: '/',
    name: 'dashboard',
    component: Dashboard,
    meta: { title: '仪表盘', icon: 'Odometer', group: '概览' },
  },
  {
    path: '/import',
    name: 'import',
    component: Import,
    meta: { title: '导入邮箱', icon: 'Upload', group: '注册' },
  },
  {
    path: '/invites',
    name: 'invites',
    component: InvitePool,
    meta: { title: '邀请码池', icon: 'Ticket', group: '注册' },
  },
  {
    path: '/register',
    name: 'register',
    component: Register,
    meta: { title: '单次注册', icon: 'VideoPlay', group: '注册' },
  },
  {
    path: '/auto',
    name: 'auto',
    component: AutoLoop,
    meta: { title: '全自动批量', icon: 'MagicStick', group: '注册' },
  },
  {
    path: '/proxy',
    name: 'proxy',
    component: ProxyPool,
    meta: { title: '代理池', icon: 'Connection', group: '注册' },
  },
  {
    path: '/pool',
    name: 'pool',
    component: Pool,
    meta: { title: '邮箱列表', icon: 'Files', group: '数据' },
  },
  {
    path: '/registered',
    name: 'registered',
    component: Registered,
    meta: { title: '注册结果', icon: 'CircleCheck', group: '数据' },
  },
  {
    path: '/runs',
    name: 'runs',
    component: Runs,
    meta: { title: '运行记录', icon: 'Document', group: '数据' },
  },
  {
    path: '/settings/mail',
    name: 'mail',
    component: MailConfig,
    meta: { title: '邮箱配置', icon: 'Message', group: '配置' },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  NProgress.start()
  if (to.meta?.title) document.title = `${to.meta.title} · Muse Register`
  next()
})
router.afterEach(() => {
  NProgress.done()
})

export default router
