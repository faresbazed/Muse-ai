<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useThemeStore } from '@/stores/theme'
import { useStatsStore } from '@/stores/stats'
import { useRuntimeStore } from '@/stores/runtime'
import { useLocaleStore } from '@/stores/locale'
import { translateUiText } from '@/ui-translations'
import captainLogo from '@/assets/captain-logo.png'

const route = useRoute()
const router = useRouter()
const theme = useThemeStore()
const statsStore = useStatsStore()
const runtime = useRuntimeStore()
const localeStore = useLocaleStore()
const { stats, invites, registered } = storeToRefs(statsStore)
const { banner } = storeToRefs(runtime)
const { locale } = storeToRefs(localeStore)

watch([() => route.meta.title, locale], ([title, language]) => {
  document.title = `${translateUiText(title || 'Muse JP Reg', language)} · Muse JP Reg`
}, { immediate: true })

const collapse = ref(false)
const mobileViewport = typeof window !== 'undefined'
  ? window.matchMedia('(max-width: 768px)')
  : null
const isMobile = ref(mobileViewport?.matches || false)
function syncSidebarToViewport(event) {
  isMobile.value = event.matches
  collapse.value = event.matches
}
watch(() => route.path, () => {
  if (isMobile.value) collapse.value = true
})
function closeMobileMenu(event) {
  if (event.key === 'Escape' && isMobile.value && !collapse.value) {
    collapse.value = true
    document.querySelector('.menu-toggle')?.focus()
  }
}
watch([isMobile, collapse], async ([mobile, collapsed], previous, onCleanup) => {
  if (!mobile || collapsed) return
  const previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  onCleanup(() => { document.body.style.overflow = previousOverflow })
  await nextTick()
  document.querySelector('.sidebar [role="menuitem"]')?.focus()
})
const tipDismissed = ref(false)

const GROUP_ORDER = ['概览', '注册', '数据', '配置']
const groups = computed(() => {
  const map = {}
  for (const r of router.getRoutes()) {
    if (!r.meta?.title) continue
    const g = r.meta.group || '其他'
    ;(map[g] ||= []).push(r)
  }
  return GROUP_ORDER.filter((g) => map[g]).map((g) => ({ name: g, items: map[g] }))
})

const activeMenu = computed(() => route.path)
const crumb = computed(() => [route.meta.group, route.meta.title].filter(Boolean))

const menuOptions = computed(() =>
  router.getRoutes()
    .filter((r) => r.meta?.title)
    .map((r) => ({ value: r.path, label: `${translateUiText(r.meta.group, locale.value)} / ${translateUiText(r.meta.title, locale.value)}` })),
)
const search = ref('')
function onSearch(path) {
  if (path) router.push(path)
  search.value = ''
}

const statPills = computed(() => [
  { label: '可用邮箱', value: stats.value.available, type: 'success' },
  { label: '进行中', value: stats.value.in_use, type: 'warning' },
  { label: '已成号', value: registered.value.total, type: 'primary' },
  { label: '可兑余量', value: invites.value.remaining_uses, type: 'info' },
])

onMounted(() => {
  theme.apply()
  if (mobileViewport) {
    collapse.value = mobileViewport.matches
    mobileViewport.addEventListener('change', syncSidebarToViewport)
  }
  window.addEventListener('keydown', closeMobileMenu)
  statsStore.startPolling()
  runtime.connectAutoStream()
})

onUnmounted(() => {
  window.removeEventListener('keydown', closeMobileMenu)
  mobileViewport?.removeEventListener('change', syncSidebarToViewport)
})
</script>
<template>
  <el-container class="admin">
    <button v-if="isMobile && !collapse" class="nav-backdrop" aria-label="关闭菜单" @click="collapse = true" />
    <el-aside
      id="main-navigation" :width="isMobile ? '260px' : (collapse ? '64px' : '220px')"
      class="sidebar" role="navigation" aria-label="主导航" :class="{ 'mobile-open': isMobile && !collapse }"
      :inert="isMobile && collapse" :aria-hidden="isMobile && collapse ? 'true' : undefined"
    >
      <div class="brand" :class="{ mini: collapse && !isMobile }">
        <span class="logo">
          <img :src="captainLogo" alt="logo" class="logo-img" />
        </span>
        <span v-if="!collapse || isMobile" class="brand-name">Muse JP Reg</span>
      </div>
      <el-scrollbar>
        <el-menu :default-active="activeMenu" router :collapse="collapse && !isMobile" class="side-menu">
          <el-menu-item-group v-for="grp in groups" :key="grp.name" :title="collapse ? '' : grp.name">
            <el-menu-item v-for="r in grp.items" :key="r.path" :index="r.path">
              <el-icon><component :is="r.meta.icon" /></el-icon>
              <template #title>{{ r.meta.title }}</template>
            </el-menu-item>
          </el-menu-item-group>
        </el-menu>
      </el-scrollbar>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div class="left">
          <el-button text class="menu-toggle" aria-label="切换菜单" aria-controls="main-navigation" :aria-expanded="!collapse" @click="collapse = !collapse">
            <el-icon :size="18"><Fold v-if="!collapse" /><Expand v-else /></el-icon>
          </el-button>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item v-for="c in crumb" :key="c">{{ c }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="right">
          <el-select
            v-model="search" filterable clearable placeholder="搜索菜单"
            size="small" class="search-box" @change="onSearch"
          >
            <el-option v-for="o in menuOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
          <el-select v-model="locale" size="small" class="locale-select" aria-label="Language">
            <el-option label="简体中文" value="zh-CN" />
            <el-option label="العربية" value="ar" />
          </el-select>
          <div class="pills">
            <el-tag v-for="p in statPills" :key="p.label" :type="p.type" size="small" effect="plain">
              {{ p.label }} <b>{{ p.value }}</b>
            </el-tag>
          </div>
          <el-tooltip :content="theme.dark ? '浅色模式' : '深色模式'">
            <el-button circle text :aria-label="translateUiText(theme.dark ? '浅色模式' : '深色模式', locale)" @click="theme.toggle">
              <el-icon :size="18"><Moon v-if="!theme.dark" /><Sunny v-else /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </el-header>

      <el-main class="content">
        <div v-if="!tipDismissed" class="tip-banner">
          <div class="tip-content">
            <el-icon :size="16" style="color: #409eff; flex-shrink: 0"><InfoFilled /></el-icon>
            <span>
              <b>协议提示</b>：注册 <code>muse.ai</code> 请优先使用 <b>日本 (JP) 代理节点</b>（免绑卡直过）；非开放地区引导后会进入 <code>waitlist</code> 候补状态。
            </span>
          </div>
          <el-button text size="small" class="tip-close" @click="tipDismissed = true">
            <el-icon :size="14"><Close /></el-icon>
          </el-button>
        </div>
        <el-alert
          v-if="banner" :title="banner" type="warning" show-icon
          class="circuit-banner" @close="runtime.dismissBanner"
        />
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.admin { min-height: 100vh; min-height: 100dvh; }
.admin > .el-container { min-width: 0; }
.menu-toggle { flex-shrink: 0; }
.nav-backdrop { position: fixed; inset: 0; background: #0007; border: 0; z-index: 1000; }
.sidebar {
  background: var(--app-sidebar-bg);
  border-right: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  transition: width 0.2s;
}
.brand {
  height: 56px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
  font-size: 16px;
  font-weight: 600;
  color: var(--app-title);
  border-bottom: 1px solid var(--app-border);
  white-space: nowrap;
  overflow: hidden;
}
.brand .logo {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: #0a1128;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
}
.brand .logo .logo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.brand.mini { justify-content: center; padding: 0; }
.side-menu { border-right: none; }
.side-menu :deep(.el-menu-item) { white-space: normal; line-height: 1.6; height: auto; min-height: 48px; padding: 12px 16px !important; }
.side-menu :deep(.el-menu-item span) { min-width: 0; overflow-wrap: anywhere; }
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--app-header-bg);
  border-bottom: 1px solid var(--app-border);
  padding: 0 16px;
}
.topbar .left { display: flex; align-items: center; gap: 12px; }
.topbar .right { display: flex; align-items: center; gap: 14px; }
.search-box { width: 180px; }
.locale-select { width: 124px; }
.pills { display: flex; gap: 6px; }
.pills b { color: inherit; }
.content { background: var(--app-content-bg); padding: 16px; }
.circuit-banner { margin-bottom: 14px; }
.tip-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  margin-bottom: 14px;
  border-radius: 6px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.tip-content {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.tip-close { flex-shrink: 0; }
@media (max-width: 1199px) {
  .pills, .search-box { display: none; }
}
@media (max-width: 768px) {
  .sidebar { position: fixed; inset-block: 0; inset-inline-start: 0; z-index: 1001; visibility: hidden; transform: translateX(-100%); transition: transform .2s, visibility .2s; }
  :global(html[dir="rtl"] .sidebar) { transform: translateX(100%); }
  .sidebar.mobile-open { visibility: visible; transform: translateX(0); }
  :global(html[dir="rtl"] .sidebar.mobile-open) { transform: translateX(0); }
  .topbar { position: sticky; top: 0; z-index: 100; height: auto; min-height: 60px; gap: 8px; padding: 6px 10px; }
  .topbar .left { min-width: 0; gap: 6px; }
  .topbar .right { flex-shrink: 0; gap: 4px; }
  .topbar :deep(.el-breadcrumb) { min-width: 0; font-size: 12px; line-height: 1.5; }
  .topbar :deep(.el-breadcrumb__item:not(:last-child)) { display: none; }
  .topbar :deep(.el-breadcrumb__inner) { overflow-wrap: anywhere; }
  .locale-select { width: 108px; }
  .content { padding: 10px; }
  .brand { min-height: 60px; }
  .tip-banner { padding: 10px; }
  .tip-content { min-width: 0; line-height: 1.7; }
  .side-menu :deep(.el-menu-item) { white-space: normal; line-height: 1.6; min-height: 48px; height: auto; padding-block: 12px; }
}
</style>
