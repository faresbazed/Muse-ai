<script setup>
import { useCompactLayout } from '@/composables/useCompactLayout'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { autoStart, autoPause, autoResume, autoStop } from '@/api/register'
import { useFormStore, proxyText } from '@/stores/form'
import { useProxyStore } from '@/stores/proxy'
import { useStatsStore } from '@/stores/stats'
import { useRuntimeStore } from '@/stores/runtime'
import LogPanel from '@/components/LogPanel.vue'
import StatusDot from '@/components/StatusDot.vue'

const compact = useCompactLayout()
const router = useRouter()
const { form } = storeToRefs(useFormStore())
const proxyStore = useProxyStore()
const { count: proxyCount } = storeToRefs(proxyStore)
const { invites } = storeToRefs(useStatsStore())
const runtime = useRuntimeStore()
const { autoStatus } = storeToRefs(runtime)

const st = computed(() => autoStatus.value.state || 'stopped')
const canStart = computed(() => st.value === 'stopped')
const canPause = computed(() => st.value === 'running')
const canResume = computed(() => st.value === 'paused')
const canStop = computed(() => st.value !== 'stopped')

const stateLabel = computed(() => ({
  stopped: '未运行', running: '运行中', paused: '已暂停',
}[st.value] || st.value))
const stateType = computed(() => ({
  stopped: 'info', running: 'success', paused: 'warning',
}[st.value] || 'info'))

const workers = computed(() => Array.isArray(autoStatus.value.workers) ? autoStatus.value.workers : [])

async function start() {
  try {
    await autoStart({
      proxy: proxyText(form.value),
      proxy_pool: proxyStore.text,
      concurrency: parseInt(form.value.autoConcurrency, 10) || 5,
      max_per_ip: parseInt(form.value.autoMaxPerIp, 10) || 6,
      otp_timeout: parseInt(form.value.otpTimeout, 10) || 45,
      cool_down_seconds: parseFloat(form.value.autoCoolDown) || 0,
      target_count: parseInt(form.value.autoTargetCount, 10) || 0,
      lang: form.value.lang || 'ja',
      impersonate: form.value.impersonate || 'chrome142',
      send_caa: !!form.value.autoSendCaa,
      send_falco: !!form.value.autoSendFalco,
      resolve_ip: !!form.value.autoResolveIp,
      redeem_mode: form.value.autoRedeemMode || 'pool',
      auto_pool_own_code: !!form.value.autoPoolOwnCodeBatch,
      stop_on_reject: !!form.value.autoStopOnReject,
    })
    ElMessage.success('Muse 批量调度已启动')
  } catch (e) { ElMessage.error('启动失败: ' + e.message) }
}

async function call(fn, name) {
  try {
    await fn()
    if (name === '恢复') runtime.dismissBanner()
    ElMessage.success(name + ' 成功')
  } catch (e) { ElMessage.error(name + ' 失败: ' + e.message) }
}
</script>

<template>
  <div class="page">
    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header><span class="section-title" style="margin: 0">全自动批量注册与裂变调度</span></template>

      <el-space wrap :size="16" style="margin-bottom: 14px">
        <el-form-item label="并发 Worker" style="margin: 0">
          <el-input-number v-model="form.autoConcurrency" :min="1" :max="20" />
        </el-form-item>
        <el-form-item label="单 IP 上限 (max_per_ip)" style="margin: 0">
          <el-input-number v-model="form.autoMaxPerIp" :min="1" :max="50" />
        </el-form-item>
        <el-form-item label="目标成功数 (0=不限)" style="margin: 0">
          <el-input-number v-model="form.autoTargetCount" :min="0" :max="100000" />
        </el-form-item>
        <el-form-item label="OTP 超时(秒)" style="margin: 0">
          <el-input-number v-model="form.otpTimeout" :min="15" :max="300" />
        </el-form-item>
        <el-form-item label="冷却(秒)" style="margin: 0">
          <el-input-number v-model="form.autoCoolDown" :min="0" :max="120" />
        </el-form-item>
      </el-space>

      <el-form-item label="邀请码与裂变策略" style="margin-bottom: 12px">
        <div style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap">
          <el-radio-group v-model="form.autoRedeemMode">
            <el-radio value="pool">从邀请码池自动兑换（余 {{ invites.remaining_uses }} 次）</el-radio>
            <el-radio value="none">仅注册激活（不兑码）</el-radio>
          </el-radio-group>
          <el-checkbox v-if="form.autoRedeemMode === 'pool'" v-model="form.autoPoolOwnCodeBatch">
            新号产出的自有邀请码自动入池裂变
          </el-checkbox>
          <el-button size="small" @click="router.push('/invites')">管理邀请码池</el-button>
        </div>
      </el-form-item>

      <el-form-item label="调度保护与协议选项" style="margin-bottom: 12px">
        <el-space wrap :size="18">
          <el-checkbox v-model="form.autoStopOnReject">
            严格停批保护（遇地区 waitlist / 服务端拒绝 / 发码后异常自动暂停防烧号）
          </el-checkbox>
          <el-checkbox v-model="form.autoResolveIp">检测出口 IP (ipify)</el-checkbox>
          <el-checkbox v-model="form.autoSendCaa">上报 CAA 漏斗埋点</el-checkbox>
          <el-checkbox v-model="form.autoSendFalco">上报 Falco 交互事件</el-checkbox>
        </el-space>
        <div class="hint" style="width: 100%; margin-top: 4px">
          对齐 <code>muse-protocol</code> 调度语义：每个 Worker 独占一条 sticky 代理，成号满 <code>max_per_ip</code> 自动轮换下一条；发码前的网络抖动会自动换代理同邮箱重试最多 3 次，不消耗新邮箱。
        </div>
      </el-form-item>

      <el-form-item label="代理池状态" style="margin-bottom: 12px">
        <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap">
          <el-tag :type="proxyCount ? 'success' : 'warning'" effect="light">
            {{ proxyCount ? `代理池已配 ${proxyCount} 条` : '代理池为空' }}
          </el-tag>
          <span class="hint">
            {{ proxyCount ? 'Worker 独占 sticky 认领并按 max_per_ip 自动轮换' : '将回退使用「单次注册」页填写的单条代理' }}
          </span>
          <el-button size="small" @click="router.push('/proxy')">管理代理池</el-button>
        </div>
      </el-form-item>

      <el-space wrap style="margin-top: 6px">
        <el-button type="primary" :disabled="!canStart" @click="start">启动批量</el-button>
        <el-button :disabled="!canPause" @click="call(autoPause, '暂停')">暂停</el-button>
        <el-button type="success" plain :disabled="!canResume" @click="call(autoResume, '恢复')">恢复运行</el-button>
        <el-button type="danger" :disabled="!canStop" @click="call(autoStop, '停止')">停止</el-button>
      </el-space>

      <el-descriptions :column="compact ? 1 : 6" border size="small" style="margin-top: 16px">
        <el-descriptions-item label="状态"><StatusDot :type="stateType" :text="stateLabel" /></el-descriptions-item>
        <el-descriptions-item label="成功">
          <b style="color: var(--el-color-success)">{{ autoStatus.registered_ok || 0 }}</b>
          <span v-if="autoStatus.target_count"> / {{ autoStatus.target_count }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="地区受限">
          <b style="color: var(--el-color-warning)">{{ autoStatus.registered_waitlist || 0 }}</b>
        </el-descriptions-item>
        <el-descriptions-item label="失败">
          <b style="color: var(--el-color-danger)">{{ autoStatus.registered_fail || 0 }}</b>
        </el-descriptions-item>
        <el-descriptions-item label="换IP次数">{{ autoStatus.ip_switches || 0 }}</el-descriptions-item>
        <el-descriptions-item label="并发">{{ autoStatus.concurrency || 1 }}</el-descriptions-item>
      </el-descriptions>

      <div v-if="workers.length" style="margin-top: 12px">
        <el-tag v-for="w in workers" :key="w.id" type="primary" effect="plain" style="margin: 0 6px 6px 0">
          W{{ w.id }} · {{ w.email }} · {{ w.proxy }} ({{ w.uses }}/{{ autoStatus.max_per_ip || form.autoMaxPerIp }})
        </el-tag>
      </div>
      <p v-if="autoStatus.last_message" class="hint" style="margin-top: 8px">{{ autoStatus.last_message }}</p>
    </el-card>

    <el-card shadow="never">
      <LogPanel />
    </el-card>
  </div>
</template>
