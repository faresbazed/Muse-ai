<script setup>
import { onActivated, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { listRuns } from '@/api/register'
import { fmtTime } from '@/api/request'
import { useRuntimeStore } from '@/stores/runtime'
import StatusDot from '@/components/StatusDot.vue'

const { dataVersion } = storeToRefs(useRuntimeStore())
const rows = ref([])
const loading = ref(false)

const STATUS_TYPE = { done: 'success', failed: 'danger', running: 'warning' }

async function load() {
  loading.value = true
  try { const { items } = await listRuns(60); rows.value = items }
  catch (e) { ElMessage.error(e.message) }
  finally { loading.value = false }
}

watch(dataVersion, () => load())
onActivated(() => load())
</script>

<template>
  <div class="page">
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; align-items: center; justify-content: space-between">
          <span class="section-title" style="margin: 0">运行记录</span>
          <el-button size="small" @click="load"><el-icon><Refresh /></el-icon>刷新</el-button>
        </div>
      </template>
      <p class="table-scroll-hint">横向滑动查看全部列</p>
      <el-skeleton v-if="loading && !rows.length" :rows="6" animated style="padding: 8px 0" />

      <el-table v-else v-loading="loading" :data="rows" size="small" stripe>
        <el-table-column prop="run_id" label="Run ID" width="145">
          <template #default="{ row }"><span class="mono">{{ row.run_id }}</span></template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="200" show-overflow-tooltip>
          <template #default="{ row }"><span dir="ltr">{{ row.email }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="95">
          <template #default="{ row }">
            <StatusDot :type="STATUS_TYPE[row.status] || 'info'" :text="row.status" />
          </template>
        </el-table-column>
        <el-table-column prop="stage" label="最终阶段" width="145">
          <template #default="{ row }">
            <span v-if="row.stage" class="mono" style="font-size: 12px">{{ row.stage }}</span>
            <span v-else class="hint">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="error_category" label="分类" width="135">
          <template #default="{ row }">
            <el-tag v-if="row.error_category" size="small" type="warning" effect="plain">{{ row.error_category }}</el-tag>
            <span v-else class="hint">—</span>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column prop="error" label="备注 / 错误详情" min-width="220" show-overflow-tooltip />
        <template #empty>
          <el-empty description="暂无运行记录" :image-size="70" />
        </template>
      </el-table>
    </el-card>
  </div>
</template>
