<script setup>
import { useCompactLayout } from '@/composables/useCompactLayout'
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { useStatsStore } from '@/stores/stats'
import { useRuntimeStore } from '@/stores/runtime'
import StatusDot from '@/components/StatusDot.vue'

const compact = useCompactLayout()
const router = useRouter()
const { stats, invites, registered } = storeToRefs(useStatsStore())
const { autoStatus } = storeToRefs(useRuntimeStore())

const cards = computed(() => [
  { label: '可用邮箱池', value: stats.value.available, color: '#4caf50', icon: 'Message', to: '/pool' },
  { label: '进行中邮箱', value: stats.value.in_use, color: '#ff9800', icon: 'Loading', to: '/pool' },
  { label: '已成号总计', value: registered.value.total, color: 'var(--brand)', icon: 'CircleCheck', to: '/registered' },
  { label: '已兑换全权号', value: registered.value.redeemed, color: '#2196f3', icon: 'Select', to: '/registered' },
  { label: '已产出邀请码', value: registered.value.own_codes, color: '#9c27b0', icon: 'Ticket', to: '/registered' },
  { label: '池内可兑次数', value: invites.value.remaining_uses, color: '#00acc1', icon: 'Present', to: '/invites' },
])

const autoStateLabel = computed(() => ({
  stopped: '未运行', running: '运行中', paused: '已暂停',
}[autoStatus.value.state] || autoStatus.value.state))
const autoStateType = computed(() => ({
  stopped: 'info', running: 'success', paused: 'warning',
}[autoStatus.value.state] || 'info'))
</script>

<template>
  <div class="page">
    <el-row :gutter="16">
      <el-col v-for="c in cards" :key="c.label" :xs="12" :sm="8" :md="4" style="margin-bottom: 16px">
        <el-card class="stat-card" shadow="hover" style="cursor: pointer" @click="router.push(c.to)">
          <div style="display: flex; align-items: center; justify-content: space-between">
            <div>
              <div class="stat-value" :style="{ color: c.color }">{{ c.value }}</div>
              <div class="stat-label">{{ c.label }}</div>
            </div>
            <el-icon :size="28" :style="{ color: c.color, opacity: 0.55 }"><component :is="c.icon" /></el-icon>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :md="12" style="margin-bottom: 16px">
        <el-card shadow="never">
          <template #header><span class="section-title" style="margin: 0">全自动批量调度状态</span></template>
          <el-descriptions :column="compact ? 1 : 3" border size="small">
            <el-descriptions-item label="状态"><StatusDot :type="autoStateType" :text="autoStateLabel" /></el-descriptions-item>
            <el-descriptions-item label="并发 Worker">{{ autoStatus.concurrency || 1 }}</el-descriptions-item>
            <el-descriptions-item label="换 IP 次数">{{ autoStatus.ip_switches || 0 }}</el-descriptions-item>
            <el-descriptions-item label="成功">
              <b style="color: var(--el-color-success)">{{ autoStatus.registered_ok || 0 }}</b>
            </el-descriptions-item>
            <el-descriptions-item label="地区受限">
              <b style="color: var(--el-color-warning)">{{ autoStatus.registered_waitlist || 0 }}</b>
            </el-descriptions-item>
            <el-descriptions-item label="失败">
              <b style="color: var(--el-color-danger)">{{ autoStatus.registered_fail || 0 }}</b>
            </el-descriptions-item>
          </el-descriptions>
          <div style="margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap">
            <el-button type="primary" @click="router.push('/auto')">前往全自动批量</el-button>
            <el-button @click="router.push('/register')">单次注册调试</el-button>
          </div>
        </el-card>
      </el-col>

      <el-col :md="12" style="margin-bottom: 16px">
        <el-card shadow="never">
          <template #header><span class="section-title" style="margin: 0">快捷准备与管理</span></template>
          <el-space wrap>
            <el-button type="success" plain @click="router.push('/import')"><el-icon><Upload /></el-icon>导入 / 同步 4173 邮箱</el-button>
            <el-button type="primary" plain @click="router.push('/invites')"><el-icon><Ticket /></el-icon>管理邀请码池</el-button>
            <el-button @click="router.push('/proxy')"><el-icon><Connection /></el-icon>配置 JP 代理池</el-button>
            <el-button @click="router.push('/registered')"><el-icon><CircleCheck /></el-icon>查看凭证与导出</el-button>
          </el-space>
          <div class="hint" style="margin-top: 14px; line-height: 1.7">
            <b>完整协议链路</b>：<code>GET /</code> → <code>restart</code> → <code>send-otp</code> → <code>confirm-otp</code> → <code>register-completion</code> → <code>auth.meta.com/hatch/session/bootstrap</code>（动态披露 &amp; 地区检测）→ <code>accept-tos</code> → <code>vm/wake</code> → <code>redeem</code> → 提取本号专属邀请码自动裂变入池。
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>
