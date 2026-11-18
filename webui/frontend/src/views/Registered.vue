<script setup>
import { computed, onActivated, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listRegistered, getRegistered, deleteRegistered,
  bulkDeleteRegistered, bulkDeleteAccounts, checkLive,
  redeemRegistered, listExportFormats, exportRegistered,
} from '@/api/register'
import { copyText, fmtTime } from '@/api/request'
import { useFormStore, proxyText } from '@/stores/form'
import { useProxyStore } from '@/stores/proxy'
import { useStatsStore } from '@/stores/stats'
import { useRuntimeStore } from '@/stores/runtime'
import StatusDot from '@/components/StatusDot.vue'

const { form } = storeToRefs(useFormStore())
const { list: proxyList } = storeToRefs(useProxyStore())
const statsStore = useStatsStore()
const { invites } = storeToRefs(statsStore)
const runtime = useRuntimeStore()
const { dataVersion } = storeToRefs(runtime)

const PAGE_SIZE = 20
const rows = ref([])
const total = ref(0)
const summary = ref({ total: 0, redeemed: 0, activated: 0, waitlist: 0, own_codes: 0 })
const page = ref(1)
const filter = ref('all')
const selected = ref([])
const loading = ref(false)
const checking = ref(false)
const checkResult = ref('')

const REG_STATUS = {
  redeemed: { type: 'success', text: '已兑换' },
  activated: { type: 'primary', text: '已激活' },
  registered_pending_redemption: { type: 'warning', text: '待兑码' },
  registered_waitlist: { type: 'danger', text: '地区受限' },
  registered_unactivated: { type: 'info', text: '未引导' },
}

const LIVE_TYPE = {
  live: 'success',
  forbidden: 'warning',
  token_invalid: 'danger',
  error: 'danger',
}

function liveOf(row) { return row.live_check || null }

async function load(resetPage) {
  if (resetPage) page.value = 1
  loading.value = true
  try {
    const r = await listRegistered({
      limit: PAGE_SIZE,
      offset: (page.value - 1) * PAGE_SIZE,
      filter: filter.value,
    })
    rows.value = r.items || []
    total.value = r.total || 0
    if (r.summary) summary.value = r.summary
  } catch (e) { ElMessage.error(e.message) }
  finally { loading.value = false }
}

function collectEmails(mode) {
  if (mode === 'selected') return selected.value.map((r) => r.email)
  if (mode === 'unchecked') return rows.value.filter((r) => !liveOf(r)).map((r) => r.email)
  return rows.value.map((r) => r.email)
}

async function doCheck(mode) {
  const emails = collectEmails(mode)
  if (!emails.length) { ElMessage.info('当前没有需要测活的账号'); return }
  checking.value = true
  checkResult.value = `测活中... (${emails.length} 个)`
  try {
    const { results, pooled_new } = await checkLive({
      emails,
      proxy: proxyText(form.value),
      fetch_own_code: true,
      auto_pool_own_code: !!form.value.autoPoolOwnCode,
    })
    let live = 0, forbidden = 0, invalid = 0, err = 0
    for (const [email, info] of Object.entries(results)) {
      const row = rows.value.find((r) => r.email === email)
      if (row) {
        row.live_check = info
        if (info.own_code && !row.own_code) row.own_code = info.own_code
      }
      if (info.status === 'live') live++
      else if (info.status === 'forbidden') forbidden++
      else if (info.status === 'token_invalid') invalid++
      else err++
    }
    const parts = [`完成: ${live} 活号(200), ${forbidden} 无权限(403), ${invalid} 失效(401)`]
    if (err) parts.push(`${err} 网络异常`)
    if (pooled_new) parts.push(`新回流邀请码 ${pooled_new} 枚`)
    checkResult.value = parts.join(' · ')
    statsStore.refresh()
  } catch (e) {
    checkResult.value = ''
    ElMessage.error('测活失败: ' + e.message)
  } finally { checking.value = false }
}

// ──────────── 补兑邀请码弹窗 ────────────
const redeemVisible = ref(false)
const redeemSaving = ref(false)
const redeemEmails = ref([])
const redeemMode = ref('pool')
const redeemCode = ref('')
const redeemAutoPool = ref(true)

function openRedeemOne(row) {
  redeemEmails.value = [row.email]
  redeemMode.value = invites.value.remaining_uses > 0 ? 'pool' : 'single'
  redeemVisible.value = true
}

function openRedeemSelected() {
  const emails = selected.value.map((r) => r.email)
  if (!emails.length) return
  redeemEmails.value = emails
  redeemMode.value = invites.value.remaining_uses > 0 ? 'pool' : 'single'
  redeemVisible.value = true
}

async function submitRedeem() {
  if (redeemMode.value === 'single' && !redeemCode.value.trim()) {
    ElMessage.warning('请输入要兑换的邀请码')
    return
  }
  redeemSaving.value = true
  try {
    const r = await redeemRegistered({
      emails: redeemEmails.value,
      redeem_mode: redeemMode.value,
      invite_code: redeemCode.value.trim(),
      proxy: proxyText(form.value),
      auto_pool_own_code: redeemAutoPool.value,
    })
    ElMessage.success(
      `兑换成功 ${r.redeemed} 个，失败 ${r.failed} 个` +
      (r.harvested_codes?.length ? `，产出新邀请码 ${r.harvested_codes.length} 枚` : ''),
    )
    redeemVisible.value = false
    statsStore.refresh()
    await load(false)
  } catch (e) {
    ElMessage.error('补兑失败: ' + e.message)
  } finally {
    redeemSaving.value = false
  }
}

async function confirm(msg) {
  try {
    await ElMessageBox.confirm(msg, '确认', {
      type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消',
      customClass: 'confirm-multiline',
    })
    return true
  } catch (_) { return false }
}

async function deleteOne(email) {
  if (!(await confirm(`删除 ${email} 的注册结果？`))) return
  try { await deleteRegistered(email); ElMessage.success('已删除'); statsStore.refresh(); load() }
  catch (e) { ElMessage.error(e.message) }
}

async function deleteSelected() {
  const emails = selected.value.map((r) => r.email)
  if (!emails.length) return
  if (!(await confirm(`确定删除选中的 ${emails.length} 条记录？(不可恢复)`))) return
  try { const r = await bulkDeleteRegistered({ emails }); ElMessage.success(`已删除 ${r.deleted} 条`); statsStore.refresh(); load() }
  catch (e) { ElMessage.error(e.message) }
}

async function deleteAll() {
  if (!(await confirm('确定清空注册结果表里的全部凭证？此操作不可恢复！'))) return
  try { const r = await bulkDeleteRegistered({ all: true }); ElMessage.success(`已清空 ${r.deleted} 条`); statsStore.refresh(); load(true) }
  catch (e) { ElMessage.error(e.message) }
}

// ──────────── 批量导出 ────────────
const exportFormats = ref([])
const exporting = ref(false)
const exportVisible = ref(false)
const exportText = ref('')
const exportCount = ref(0)
const exportFilename = ref('')
const exportLabel = ref('')
const exportedEmails = ref([])
const deletingExported = ref(false)

const exportBtnText = computed(() =>
  selected.value.length ? `导出选中 (${selected.value.length})` : '导出全部',
)

async function loadExportFormats() {
  if (exportFormats.value.length) return
  try {
    const { formats } = await listExportFormats()
    exportFormats.value = formats || []
  } catch (e) { ElMessage.error('加载导出格式失败: ' + e.message) }
}

async function doExport(fmt) {
  const emails = selected.value.map((r) => r.email)
  const payload = emails.length ? { format: fmt.id, emails } : { format: fmt.id, all: true }
  exporting.value = true
  try {
    const r = await exportRegistered(payload)
    exportedEmails.value = (r.emails || []).filter(Boolean)
    if (r.mode === 'download') {
      saveBlob(b64ToBytes(r.b64), r.filename, r.mime)
      ElMessage.success(`已下载 ${r.filename}（${r.count} 个账号）`)
      return
    }
    exportText.value = r.text || ''
    exportCount.value = r.count || 0
    exportFilename.value = r.filename || 'export.txt'
    exportLabel.value = r.label || fmt.label
    exportVisible.value = true
  } catch (e) { ElMessage.error('导出失败: ' + e.message) }
  finally { exporting.value = false }
}

function b64ToBytes(b64) {
  const bin = atob(b64 || '')
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return bytes
}

function saveBlob(data, filename, mime) {
  const blob = data instanceof Blob ? data : new Blob([data], { type: mime || 'application/octet-stream' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function downloadExport() {
  saveBlob(exportText.value, exportFilename.value, 'text/plain;charset=utf-8')
}

async function downloadAndDelete() {
  downloadExport()
  const emails = exportedEmails.value
  if (!emails.length) return
  const ok = await confirm(
    `已下载 ${exportFilename.value}。\n\n确定同时从「注册结果」与「邮箱列表」删除这 ${emails.length} 个账号吗？（不可恢复）`,
  )
  if (!ok) return
  deletingExported.value = true
  try {
    const r1 = await bulkDeleteRegistered({ emails })
    let poolDeleted = 0
    try {
      const r2 = await bulkDeleteAccounts({ emails })
      poolDeleted = r2.deleted || 0
    } catch (_) {}
    ElMessage.success(`已删除：注册结果 ${r1.deleted} 条 / 邮箱列表 ${poolDeleted} 条`)
    exportVisible.value = false
    exportedEmails.value = []
    selected.value = []
    statsStore.refresh()
    load(true)
    runtime.bumpData()
  } catch (e) { ElMessage.error('删除失败: ' + e.message) }
  finally { deletingExported.value = false }
}

// ──────────── 查看完整凭证弹窗 ────────────
const credVisible = ref(false)
const credEmail = ref('')
const credData = ref(null)
const CRED_KEYS = [
  'own_code', 'used_invite_code', 'account_id', 'status', 'stage',
  'session_token', 'cookie_header', 'access_token', 'device_id',
  'ip', 'relay_url',
]
const credRows = computed(() => {
  if (!credData.value) return []
  return CRED_KEYS.filter((k) => credData.value[k]).map((k) => ({ key: k, val: String(credData.value[k]) }))
})

async function viewCred(email) {
  try {
    const { data } = await getRegistered(email)
    credData.value = data
    credEmail.value = email
    credVisible.value = true
  } catch (e) { ElMessage.error('加载凭证失败: ' + e.message) }
}

async function copyCell(email, field) {
  try {
    const { data } = await getRegistered(email)
    const val = data[field] || ''
    if (!val) { ElMessage.warning(`${field} 为空`); return }
    await copyText(val)
  } catch (e) { ElMessage.error('加载凭证失败: ' + e.message) }
}

function copyAllJson() {
  if (credData.value) copyText(JSON.stringify(credData.value, null, 2))
}

watch(page, () => load())
watch(dataVersion, () => load())
onActivated(() => load())
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px">
          <span class="section-title" style="margin: 0">Muse 注册结果</span>
          <el-space wrap>
            <el-tag size="small" type="success" effect="plain">已兑换 {{ summary.redeemed }}</el-tag>
            <el-tag size="small" type="primary" effect="plain">已激活 {{ summary.activated }}</el-tag>
            <el-tag size="small" type="warning" effect="plain">地区受限 {{ summary.waitlist }}</el-tag>
            <el-tag size="small" type="info" effect="plain">自有码 {{ summary.own_codes }}</el-tag>
          </el-space>
        </div>
      </template>

      <el-space wrap style="margin-bottom: 12px">
        <el-button @click="load(false)"><el-icon><Refresh /></el-icon>刷新</el-button>
        <el-select v-model="filter" style="width: 150px" @change="load(true)">
          <el-option label="全部账号" value="all" />
          <el-option label="已兑换全权" value="redeemed" />
          <el-option label="有自有邀请码" value="has_own_code" />
          <el-option label="已激活(未兑码)" value="activated" />
          <el-option label="地区受限(waitlist)" value="waitlist" />
          <el-option label="未测活" value="unchecked" />
          <el-option label="测活正常(200)" value="live" />
          <el-option label="无权限/失效" value="token_invalid" />
        </el-select>

        <el-select
          v-model="form.proxy" filterable clearable allow-create default-first-option
          :reserve-keyword="false" placeholder="测活/补兑代理（推荐JP）"
          style="width: 230px"
        >
          <el-option v-for="p in proxyList" :key="p" :label="p" :value="p" />
        </el-select>

        <el-button :loading="checking" @click="doCheck('unchecked')">测活未测</el-button>
        <el-button :loading="checking" @click="doCheck('all')">测活本页</el-button>
        <el-button :loading="checking" :disabled="!selected.length" @click="doCheck('selected')">
          测活选中 ({{ selected.length }})
        </el-button>

        <el-button type="success" plain :disabled="!selected.length" @click="openRedeemSelected">
          补兑邀请码 ({{ selected.length }})
        </el-button>

        <el-divider direction="vertical" />

        <el-dropdown trigger="click" @command="doExport" @visible-change="(v) => v && loadExportFormats()">
          <el-button :loading="exporting" type="primary" plain>
            <el-icon><Download /></el-icon>{{ exportBtnText }}
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="f in exportFormats" :key="f.id" :command="f" :divided="f.mode === 'download'">
                {{ f.label }}
                <span v-if="f.note" class="hint" style="margin-left: 6px">{{ f.note }}</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <el-button type="danger" plain :disabled="!selected.length" @click="deleteSelected">
          删除选中 ({{ selected.length }})
        </el-button>
        <el-button type="danger" plain @click="deleteAll">清空全部</el-button>
        <span class="hint">{{ checkResult }}</span>
      </el-space>

      <el-skeleton v-if="loading && !rows.length" :rows="6" animated style="padding: 8px 0" />
      <el-table
        v-else
        v-loading="loading" :data="rows" size="small" stripe
        @selection-change="(v) => (selected = v)"
      >
        <el-table-column type="selection" width="42" />
        <el-table-column prop="email" label="邮箱" min-width="195" show-overflow-tooltip>
          <template #default="{ row }"><span dir="ltr">{{ row.email }}</span></template>
        </el-table-column>
        <el-table-column prop="token_count" label="令牌数" width="90" align="center">
          <template #header>
            <el-tooltip content="统计 access/session/refresh/id/CSRF 五类令牌字段中已保存的数量，不显示令牌值。">
              <span>令牌数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tag size="small" type="info" effect="plain">{{ row.token_count }} / 5</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="注册状态" width="110">
          <template #default="{ row }">
            <StatusDot
              :type="(REG_STATUS[row.status] || {}).type || 'info'"
              :text="(REG_STATUS[row.status] || {}).text || row.status || '未知'"
            />
          </template>
        </el-table-column>
        <el-table-column label="自有邀请码" min-width="155">
          <template #default="{ row }">
            <el-button
              v-if="row.own_code" size="small" text type="success"
              class="cell-copy mono" @click="copyText(row.own_code)"
            >
              {{ row.own_code }}<el-icon class="ico"><CopyDocument /></el-icon>
            </el-button>
            <span v-else class="hint">—</span>
          </template>
        </el-table-column>
        <el-table-column label="Hatch测活" width="125">
          <template #default="{ row }">
            <StatusDot
              v-if="liveOf(row)"
              :type="LIVE_TYPE[liveOf(row).status] || 'info'"
              :text="liveOf(row).label"
            />
            <span v-else class="hint">—</span>
          </template>
        </el-table-column>
        <el-table-column label="Account ID" min-width="145" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.account_id" class="mono" style="font-size: 12px">{{ row.account_id }}</span>
            <span v-else class="hint">—</span>
          </template>
        </el-table-column>
        <el-table-column label="hatch_sess" width="105" align="center">
          <template #default="{ row }">
            <el-button v-if="row.st_len > 0" size="small" text type="primary" @click="copyCell(row.email, 'session_token')">
              <el-icon><CopyDocument /></el-icon>{{ row.st_len }}
            </el-button>
            <span v-else class="hint">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="ip" label="出口 IP" width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.ip" class="mono" style="font-size: 12px">{{ row.ip }}</span>
            <span v-else class="hint">—</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="155">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click="viewCred(row.email)">查看凭证</el-button>
            <el-button
              v-if="row.status !== 'redeemed' && row.st_len > 0"
              size="small" text type="success" @click="openRedeemOne(row)"
            >补兑</el-button>
            <el-button size="small" text type="danger" @click="deleteOne(row.email)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无 Muse 注册结果，去「单次注册」或「全自动批量」开始" :image-size="70" />
        </template>
      </el-table>

      <div style="display: flex; justify-content: center; margin-top: 14px">
        <el-pagination
          v-model:current-page="page" :page-size="PAGE_SIZE" :total="total"
          layout="prev, pager, next, total" background
        />
      </div>

      <!-- 导出预览弹窗 -->
      <el-dialog v-model="exportVisible" width="720px" top="8vh">
        <template #header>
          <div style="display: flex; align-items: center; gap: 12px">
            <span style="font-weight: 600">导出 · {{ exportLabel }}</span>
            <el-tag size="small" type="info">共 {{ exportCount }} 个账号</el-tag>
          </div>
        </template>
        <el-input :model-value="exportText" type="textarea" :rows="14" readonly class="mono" />
        <template #footer>
          <el-button @click="copyText(exportText)">
            <el-icon><CopyDocument /></el-icon>复制全部
          </el-button>
          <el-button type="primary" @click="downloadExport">
            <el-icon><Download /></el-icon>下载 {{ exportFilename }}
          </el-button>
          <el-button
            type="danger" plain
            :loading="deletingExported"
            :disabled="!exportedEmails.length"
            @click="downloadAndDelete"
          >
            <el-icon><Delete /></el-icon>下载并删除这 {{ exportedEmails.length }} 个号
          </el-button>
        </template>
      </el-dialog>

      <!-- 凭证详情弹窗 -->
      <el-dialog v-model="credVisible" :title="credEmail" width="760px" top="6vh">
        <template #header>
          <div style="display: flex; align-items: center; gap: 12px">
            <span class="mono" style="font-weight: 600">{{ credEmail }}</span>
            <el-button size="small" @click="copyAllJson">复制完整 JSON</el-button>
          </div>
        </template>
        <div v-for="r in credRows" :key="r.key" style="margin-bottom: 12px">
          <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 4px">
            <span class="mono" style="font-weight: 600; color: var(--brand)">{{ r.key }}</span>
            <el-tag size="small" type="info">len={{ r.val.length }}</el-tag>
            <el-button size="small" @click="copyText(r.val)">复制</el-button>
          </div>
          <el-input :model-value="r.val" :type="r.val.length > 80 ? 'textarea' : 'text'" :rows="2" readonly class="mono" />
        </div>
        <el-empty v-if="!credRows.length" description="无凭证字段" />
      </el-dialog>

      <!-- 补兑邀请码弹窗 -->
      <el-dialog v-model="redeemVisible" title="补兑 Muse 邀请码" width="520px" top="12vh">
        <p class="hint" style="margin-bottom: 14px">
          将对选中的 <b>{{ redeemEmails.length }}</b> 个账号自动执行：<code>wake_vm</code>（必调，防止误判 invalid）→ <code>stateful-sharing</code> → <code>redeem</code> → 提取本账号专属邀请码。
        </p>
        <el-form label-position="top">
          <el-form-item label="兑换来源">
            <el-radio-group v-model="redeemMode">
              <el-radio value="pool">从邀请码池取码（余 {{ invites.remaining_uses }} 次）</el-radio>
              <el-radio value="single">手动指定邀请码</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="redeemMode === 'single'" label="邀请码">
            <el-input v-model="redeemCode" class="mono" placeholder="输入有效 Muse 邀请码" />
          </el-form-item>
          <el-form-item>
            <el-checkbox v-model="redeemAutoPool">兑换后产出的自有邀请码自动加入邀请码池</el-checkbox>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="redeemVisible = false">取消</el-button>
          <el-button type="primary" :loading="redeemSaving" @click="submitRedeem">立即兑换</el-button>
        </template>
      </el-dialog>
    </el-card>
  </div>
</template>

<style scoped>
:deep(.el-button.cell-copy.el-button--small) {
  padding: 0 6px 0 0;
  height: 20px;
  font-size: 12px;
}
:deep(.cell-copy .ico) {
  margin-left: 5px;
  opacity: 0;
  transition: opacity 0.12s;
}
:deep(.cell-copy:hover .ico) { opacity: 0.65; }
</style>

<style>
.confirm-multiline .el-message-box__message { white-space: pre-line; }
</style>
