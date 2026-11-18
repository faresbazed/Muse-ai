<script setup>
import { computed, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import ar from 'element-plus/es/locale/lang/ar'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { useLocaleStore } from '@/stores/locale'
import { observeUiLocale, applyUiLocale } from '@/ui-translations'

const localeStore = useLocaleStore()
const { locale } = storeToRefs(localeStore)
const elementLocale = computed(() => locale.value === 'ar' ? ar : zhCn)

watch(locale, applyUiLocale, { immediate: true })
onMounted(observeUiLocale)
</script>

<template>
  <el-config-provider :locale="elementLocale">
    <AdminLayout />
  </el-config-provider>
</template>
