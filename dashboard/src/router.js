import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/benches' },
  {
    path: '/benches',
    name: 'BenchList',
    component: () => import('./pages/BenchList.vue'),
  },
  {
    path: '/benches/:name',
    name: 'BenchDetail',
    component: () => import('./pages/BenchDetail.vue'),
    props: true,
  },
  {
    path: '/sites',
    name: 'SiteList',
    component: () => import('./pages/SiteList.vue'),
  },
  {
    path: '/sites/:name',
    name: 'SiteDetail',
    component: () => import('./pages/SiteDetail.vue'),
    props: true,
  },
]

export default createRouter({
  history: createWebHistory('/barista/'),
  routes,
})
