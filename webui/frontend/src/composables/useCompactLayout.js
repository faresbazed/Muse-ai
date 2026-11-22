import { onScopeDispose, ref } from 'vue'

/** Keep dense status summaries readable without changing their data. */
export function useCompactLayout() {
  const media = typeof window === 'undefined' ? null : window.matchMedia('(max-width: 768px)')
  const compact = ref(media?.matches || false)
  const update = (event) => { compact.value = event.matches }
  media?.addEventListener('change', update)
  onScopeDispose(() => media?.removeEventListener('change', update))
  return compact
}
