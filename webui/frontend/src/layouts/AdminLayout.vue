<script setup>
import { computed, onMounted, ref, watch } from 'vue'
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
    .map((r) => ({ value: r.path, label: `${r.meta.group} / ${r.meta.title}` })),
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
  statsStore.startPolling()
  runtime.connectAutoStream()
})
</script>
<template>
  <el-container class="admin">
    <el-aside :width="collapse ? '64px' : '220px'" class="sidebar">
      <div class="brand" :class="{ mini: collapse }">
        <span class="logo">
          <img :src="captainLogo" alt="logo" class="logo-img" />
        </span>
        <span v-if="!collapse" class="brand-name">Muse JP Reg</span>
      </div>
      <el-scrollbar>
        <el-menu :default-active="activeMenu" router :collapse="collapse" class="side-menu">
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
          <el-button text @click="collapse = !collapse">
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
            <el-button circle text @click="theme.toggle">
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
.admin { height: 100vh; }
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
@media (max-width: 768px) {
  .pills, .search-box { display: none; }
  .topbar .right { gap: 8px; }
}
</style>
