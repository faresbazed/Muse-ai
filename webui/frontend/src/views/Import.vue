<script setup>
import { useLocaleStore } from '@/stores/locale'
import { translateUiText } from '@/ui-translations'
import { computed, onActivated, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { importAccounts, syncLocalIcloud } from '@/api/accounts'
import { getMailProviders } from '@/api/settings'
import { useStatsStore } from '@/stores/stats'
import { useRuntimeStore } from '@/stores/runtime'

const localeStore = useLocaleStore()
const statsStore = useStatsStore()
const runtime = useRuntimeStore()

const providers = ref([])
const kind = ref('icloud_relay')
const text = ref('')
const loading = ref(false)
const syncingLocal = ref(false)
const syncLimit = ref(0)
const result = ref('')
const errors = ref([])

const current = computed(
  () => providers.value.find((p) => p.kind === kind.value) || null,
)

const lineCount = computed(
  () => text.value.split('\n').filter((l) => l.trim() && !l.trim().startsWith('#')).length,
)

async function loadProviders() {
  try {
    const r = await getMailProviders(true)
    providers.value = r.providers || []
    const cur = r.current
    kind.value = providers.value.some((p) => p.kind === cur)
      ? cur
      : (providers.value[0]?.kind || 'icloud_relay')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(loadProviders)
onActivated(loadProviders)

async function doSyncLocal() {
  syncingLocal.value = true
  result.value = ''
  errors.value = []
  try {
    const r = await syncLocalIcloud(syncLimit.value || 0)
    if (!r.found) {
      result.value = '本地 iCloud 数据库中没有状态为 unused 的新邮箱'
      ElMessage.info(result.value)
    } else {
      result.value = `从本地 4173 发现 ${r.found} 个邮箱：新增 ${r.inserted}，更新 ${r.updated}，跳过 ${r.skipped}`
      ElMessage.success(`同步完成，新增 ${r.inserted} 个可用邮箱`)
    }
    statsStore.refresh()
    runtime.bumpData()
  } catch (e) {
    ElMessage.error(e.message)
    result.value = '同步失败: ' + e.message
  } finally {
    syncingLocal.value = false
  }
}

async function doImport() {
  if (!text.value.trim()) {
    ElMessage.warning('请输入要导入的邮箱行')
    return
  }
  if (!kind.value) {
    ElMessage.warning('请先选择邮箱来源')
    return
  }
  loading.value = true
  result.value = ''
  errors.value = []
  try {
    const r = await importAccounts(text.value.trim(), kind.value)
    result.value = `解析 ${r.parsed} 行，新增 ${r.inserted}，更新 ${r.updated}，跳过 ${r.skipped}`
    ElMessage.success('导入完成')
    text.value = ''
    statsStore.refresh()
    runtime.bumpData()
  } catch (e) {
    if (e.status === 422 && e.data?.errors?.length) {
      errors.value = e.data.errors
      result.value = `有 ${e.data.errors.length} 行格式不合法，整批未写入`
      ElMessage.error('导入被拒绝，请按下方提示修正')
    } else {
      result.value = '导入失败: ' + e.message
      ElMessage.error(e.message)
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header>
        <span class="section-title" style="margin: 0">一键从本地 iCloud 服务 (4173) 同步</span>
      </template>
      <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap">
        <span class="hint">数量上限（0=全部 unused）：</span>
        <el-input-number v-model="syncLimit" :min="0" :max="10000" size="small" />
        <el-button type="success" :loading="syncingLocal" @click="doSyncLocal">
          <el-icon><Refresh /></el-icon>一键同步本地 iCloud 隐藏邮箱
        </el-button>
        <span class="hint">
          自动读取本地 <code>../icloud/data/workbench.db</code> 并生成 <code>4173</code> 取件密钥写入本系统号池
        </span>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <span class="section-title" style="margin: 0">手动批量粘贴导入</span>
      </template>

      <el-form label-position="top" style="margin-bottom: 4px">
        <el-form-item label="邮箱来源">
          <el-select v-model="kind" style="width: 280px" placeholder="请选择">
            <el-option
              v-for="p in providers"
              :key="p.kind"
              :label="p.display_name"
              :value="p.kind"
            />
          </el-select>
          <span class="hint" style="margin-left: 12px">
            支持 <code>email----OTP源URL</code>（兼容 <code>muse-protocol</code> 的 <code>otp-urls.txt</code> 与第三方 iCloud 中转链接）
          </span>
        </el-form-item>
      </el-form>

      <p class="hint" v-if="current">
        每行一个，{{ current.line_segments }} 段（用 <code>----</code> 分隔）：
        <code>{{ translateUiText(current.import_hint || '', localeStore.locale) }}</code>
      </p>

      <el-input
        v-model="text"
        type="textarea"
        :rows="11"
        class="mono"
        :placeholder="current?.import_placeholder || ''"
      />

      <div style="margin-top: 12px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap">
        <el-button type="primary" :loading="loading" @click="doImport">批量导入</el-button>
        <span class="hint" v-if="lineCount">待导入 {{ lineCount }} 行</span>
        <span class="hint">{{ result }}</span>
      </div>

      <el-alert
        v-if="errors.length"
        type="error"
        :closable="true"
        show-icon
        style="margin-top: 12px"
        title="以下行格式不合法，整批已拒绝（号池未被修改）"
        @close="errors = []"
      >
        <ul class="err-list">
          <li v-for="e in errors" :key="e.line">
            <b>第 {{ e.line }} 行</b>：{{ e.error }}
          </li>
        </ul>
      </el-alert>
    </el-card>
  </div>
</template>

<style scoped>
.err-list {
  margin: 6px 0 0;
  padding-left: 18px;
  max-height: 220px;
  overflow-y: auto;
  line-height: 1.7;
}
</style>
