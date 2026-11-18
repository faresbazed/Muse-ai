import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { applyUiLocale } from '@/ui-translations'

const KEY = 'muse_ui_locale_v1'

function readSavedLocale() {
  try { return localStorage.getItem(KEY) === 'ar' ? 'ar' : 'zh-CN' } catch (_) { return 'zh-CN' }
}

export const useLocaleStore = defineStore('locale', () => {
  const locale = ref(readSavedLocale())

  function setLocale(value) {
    locale.value = value === 'ar' ? 'ar' : 'zh-CN'
  }

  watch(locale, (value) => {
    try { localStorage.setItem(KEY, value) } catch (_) {}
    applyUiLocale(value)
  }, { immediate: true, flush: 'sync' })

  return { locale, setLocale }
})
