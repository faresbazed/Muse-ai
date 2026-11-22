<script setup>
import { computed, onActivated, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { startRegister, getRegistered } from '@/api/register'
import { copyText } from '@/api/request'
import { useFormStore, proxyText } from '@/stores/form'
import { useProxyStore } from '@/stores/proxy'
import { useStatsStore } from '@/stores/stats'
import { useRuntimeStore } from '@/stores/runtime'
import LogPanel from '@/components/LogPanel.vue'

const route = useRoute()
const router = useRouter()
const { form } = storeToRefs(useFormStore())
const { list: proxyList } = storeToRefs(useProxyStore())
const { invites } = storeToRefs(useStatsStore())
const runtime = useRuntimeStore()
const { runningSingle, lastRunResult } = storeToRefs(runtime)

const starting = ref(false)
const regEmail = ref('')
const showAdvanced = ref(false)

onActivated(() => {
  if (route.query.email) regEmail.value = String(route.query.email)
  if (!String(form.value.proxy || '').trim() && proxyList.value.length > 0) {
    form.value.proxy = proxyList.value[0]
  }
})

const statusLabel = computed(() => {
  const s = lastRunResult.value?.status
  return ({
    redeemed: '已兑换全权号',
    activated: '已激活会话 (未兑码)',
    registered_pending_redemption: '已激活 (待补兑邀请码)',
    registered_waitlist: '地区受限 (waitlist 保留)',
  }[s] || s || '')
})

async function run() {
  if (form.value.redeemMode === 'single' && !String(form.value.inviteCode || '').trim()) {
    ElMessage.warning('请填写要兑换的指定邀请码，或切换为邀请码池 / 跳过兑换')
    return
  }
  starting.value = true
  runtime.clearLogs()
  lastRunResult.value = null
  try {
    const r = await startRegister({
      email: regEmail.value.trim() || null,
      proxy: proxyText(form.value),
      otp_timeout: parseInt(form.value.otpTimeout, 10) || 45,
      lang: form.value.lang || 'ja',
      impersonate: form.value.impersonate || 'chrome142',
      first_name: (form.value.firstName || '').trim(),
      last_name: (form.value.lastName || '').trim(),
      date_of_birth: (form.value.dateOfBirth || '').trim(),
      send_caa: !!form.value.sendCaa,
      send_falco: !!form.value.sendFalco,
      resolve_ip: !!form.value.resolveIp,
      redeem_mode: form.value.redeemMode || 'pool',
      invite_code: (form.value.inviteCode || '').trim(),
      auto_pool_own_code: !!form.value.autoPoolOwnCode,
    })
    runtime.addLog(`[client] 启动单次注册 run_id=${r.run_id} email=${r.email}`, 'evt')
    runtime.streamRun(r.run_id)
  } catch (e) {
    ElMessage.error(e.message)
    lastRunResult.value = { error: e.message }
  } finally {
    starting.value = false
  }
}

async function copyField(email, field) {
  try {
    const { data } = await getRegistered(email)
    const val = data[field] || ''
    if (!val) { ElMessage.warning(`${field} 为空`); return }
    await copyText(val)
  } catch (e) {
    ElMessage.error('读取凭证失败: ' + e.message)
  }
}

async function copyEmailSess(email) {
  try {
    const { data } = await getRegistered(email)
    if (!data.session_token) { ElMessage.warning('hatch_sess 为空'); return }
    await copyText(`${data.email}----${data.session_token}`)
  } catch (e) {
    ElMessage.error('读取凭证失败: ' + e.message)
  }
}
</script>

<template>
  <div class="page">
    <el-row :gutter="16">
      <el-col :md="10" style="margin-bottom: 16px">
        <el-card shadow="never">
          <template #header><span class="section-title" style="margin: 0">单次 Muse 注册</span></template>
          <el-form label-position="top">
            <el-form-item label="邮箱（留空 = 自动从号池领取下一个 available）">
              <el-input v-model="regEmail" placeholder="留空自动选号，或填指定池内邮箱" clearable />
            </el-form-item>

            <el-form-item label="代理节点（强烈建议使用日本 JP 节点；可从代理池选或手填）">
              <el-select
                v-model="form.proxy" filterable clearable allow-create default-first-option
                :reserve-keyword="false" placeholder="http://user:pass@jp-host:port 或 host:port:user:pass"
                style="width: 100%"
              >
                <el-option v-for="p in proxyList" :key="p" :label="p" :value="p" />
              </el-select>
              <div class="hint" style="margin-top: 4px">
                支持 <code>http://</code>、<code>socks5://</code>（自动转远端 DNS <code>socks5h://</code>）及 <code>host:port:user:pass</code> 四段格式。
              </div>
            </el-form-item>

            <el-form-item label="邀请码兑换策略">
              <el-radio-group v-model="form.redeemMode">
                <el-radio value="pool">
                  从邀请码池取码（余 {{ invites.remaining_uses }} 次）
                </el-radio>
                <el-radio value="single">指定邀请码</el-radio>
                <el-radio value="none">跳过兑换（仅注册激活）</el-radio>
              </el-radio-group>
              <div v-if="form.redeemMode === 'single'" style="margin-top: 8px; width: 100%">
                <el-input v-model="form.inviteCode" class="mono" placeholder="输入要兑换的 Muse 邀请码" clearable />
              </div>
              <div v-if="form.redeemMode === 'pool' && !invites.remaining_uses" class="hint" style="margin-top: 6px; color: var(--el-color-warning)">
                提示：当前邀请码池为空，将自动保留已激活账号（可先去
                <el-button link type="primary" @click="router.push('/invites')">邀请码池</el-button>
                添加种子码）。
              </div>
            </el-form-item>

            <el-form-item v-if="form.redeemMode !== 'none'">
              <div style="display: flex; align-items: center; gap: 10px">
                <el-switch v-model="form.autoPoolOwnCode" />
                <span>兑换后产出的自有邀请码自动回流至邀请码池（1 裂变 30）</span>
              </div>
            </el-form-item>

            <div style="margin-bottom: 12px">
              <el-button text size="small" type="primary" @click="showAdvanced = !showAdvanced">
                {{ showAdvanced ? '收起协议高级参数 ▲' : '展开协议高级参数（OTP超时 / 姓名生日 / 埋点）▼' }}
              </el-button>
            </div>

            <div v-if="showAdvanced" class="adv-box">
              <el-space wrap :size="12" style="margin-bottom: 10px">
                <el-form-item label="OTP 等待(秒)" style="margin: 0">
                  <el-input-number v-model="form.otpTimeout" :min="15" :max="300" size="small" />
                </el-form-item>
                <el-form-item label="语言 (Accept-Language)" style="margin: 0">
                  <el-select v-model="form.lang" size="small" style="width: 100px">
                    <el-option label="ja (推荐)" value="ja" />
                    <el-option label="en-US" value="en-US" />
                  </el-select>
                </el-form-item>
                <el-form-item label="TLS 指纹" style="margin: 0">
                  <el-select v-model="form.impersonate" size="small" style="width: 130px">
                    <el-option label="chrome142" value="chrome142" />
                    <el-option label="chrome136" value="chrome136" />
                  </el-select>
                </el-form-item>
              </el-space>

              <el-row :gutter="8" style="margin-bottom: 10px; row-gap: 8px">
                <el-col :xs="24" :sm="7">
                  <el-input v-model="form.lastName" size="small" placeholder="姓 (留空随机)" />
                </el-col>
                <el-col :xs="24" :sm="7">
                  <el-input v-model="form.firstName" size="small" placeholder="名 (留空随机)" />
                </el-col>
                <el-col :xs="24" :sm="10">
                  <el-input v-model="form.dateOfBirth" size="small" placeholder="生日 1993-11-14 (留空随机)" />
                </el-col>
              </el-row>

              <el-space wrap>
                <el-checkbox v-model="form.resolveIp" label="检测出口 IP" size="small" />
                <el-checkbox v-model="form.sendCaa" label="CAA 漏斗埋点" size="small" />
                <el-checkbox v-model="form.sendFalco" label="Falco 性能埋点" size="small" />
              </el-space>
            </div>

            <el-button type="primary" :loading="starting || runningSingle" @click="run">
              开始注册
            </el-button>
          </el-form>

          <el-alert
            v-if="lastRunResult && !lastRunResult.error"
            :type="lastRunResult.last_error ? 'warning' : 'success'"
            :closable="false"
            style="margin-top: 14px"
          >
            <div>
              <b>{{ statusLabel }}</b> · <span class="mono">{{ lastRunResult.email }}</span>
            </div>
            <div class="cred-line" v-if="lastRunResult.account_id">
              <span class="cred-label">Account ID</span>
              <code class="cred-val">{{ lastRunResult.account_id }}</code>
              <span v-if="lastRunResult.ip" class="hint" style="margin-left: 8px">IP: {{ lastRunResult.ip }}</span>
            </div>
            <div class="cred-line" v-if="lastRunResult.own_code">
              <span class="cred-label">自有邀请码</span>
              <code class="cred-val" style="font-weight: 700; color: var(--el-color-success)">{{ lastRunResult.own_code }}</code>
            </div>
            <div class="cred-line hint" v-if="lastRunResult.last_error">
              备注: {{ lastRunResult.last_error }}
            </div>
            <div style="margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap">
              <el-button size="small" @click="copyText(lastRunResult.email)">复制邮箱</el-button>
              <el-button v-if="lastRunResult.own_code" size="small" type="success" @click="copyText(lastRunResult.own_code)">
                复制自有邀请码
              </el-button>
              <el-button v-if="lastRunResult.session_token_len > 0" size="small" type="primary"
                         @click="copyField(lastRunResult.email, 'session_token')">
                复制 hatch_sess ({{ lastRunResult.session_token_len }})
              </el-button>
              <el-button v-if="lastRunResult.session_token_len > 0" size="small"
                         @click="copyEmailSess(lastRunResult.email)">
                复制 邮箱----hatch_sess
              </el-button>
            </div>
          </el-alert>

          <el-alert
            v-else-if="lastRunResult && lastRunResult.error"
            :type="lastRunResult.registered ? 'warning' : 'error'"
            :closable="false"
            style="margin-top: 14px"
            :title="lastRunResult.error"
            :description="lastRunResult.registered ? '说明：该账号已完成注册并自动保存到「注册结果」表中，未丢失凭证。' : ''"
          />
        </el-card>
      </el-col>

      <el-col :md="14" style="margin-bottom: 16px">
        <el-card shadow="never">
          <LogPanel />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.adv-box {
  padding: 12px;
  margin-bottom: 14px;
  border-radius: 6px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--app-border);
}
</style>
