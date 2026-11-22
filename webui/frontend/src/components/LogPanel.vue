<script setup>
import { useLocaleStore } from '@/stores/locale'
import { translateUiText } from '@/ui-translations'
import { nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRuntimeStore } from '@/stores/runtime'

const localeStore = useLocaleStore()
const runtime = useRuntimeStore()
const { logs } = storeToRefs(runtime)
const boxRef = ref(null)

// 新日志自动滚到底
watch(
  () => logs.value.length,
  async () => {
    await nextTick()
    const el = boxRef.value
    if (el) el.scrollTop = el.scrollHeight
  },
)
</script>

<template>
  <div class="log-wrap">
    <div class="log-head">
      <span class="section-title" style="margin: 0">实时日志</span>
      <el-button size="small" text @click="runtime.clearLogs">清空</el-button>
    </div>
    <div ref="boxRef" class="log-box">
      <div v-for="l in logs" :key="l.id" class="line" :class="l.kind">{{ l.text }}</div>
      <div v-if="!logs.length" class="line log-empty" dir="auto" style="color: #8a7">{{ translateUiText('等待日志输出…', localeStore.locale) }}</div>
    </div>
  </div>
</template>

<style scoped>
.log-empty { font-family: Tahoma, Arial, sans-serif; white-space: normal; }
.log-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
</style>
