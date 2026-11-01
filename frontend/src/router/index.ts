import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/scaffold' },
    { path: '/scaffold', name: 'scaffold', component: () => import('@/views/ScaffoldView.vue') },
    { path: '/scan', name: 'scan', component: () => import('@/views/ScanView.vue') },
    { path: '/elements', name: 'elements', component: () => import('@/views/ElementLibraryView.vue') },
    { path: '/cases', name: 'cases', component: () => import('@/views/CasesView.vue') },
    { path: '/suites', name: 'suites', component: () => import('@/views/SuitesView.vue') },
    { path: '/engines', name: 'engines', component: () => import('@/views/EnginesView.vue') },
    { path: '/executions', name: 'executions', component: () => import('@/views/ExecutionsView.vue') },
    { path: '/executions/:id/report', name: 'report', component: () => import('@/views/ReportView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/scaffold' },
  ],
})

export default router
