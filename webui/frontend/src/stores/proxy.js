import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { getProxyPool, saveProxyPool } from '@/api/proxy'

const KEY = 'muse_proxy_pool_v1'

function parseLines(s) {
  return String(s || '').split('\n').map((x) => x.trim()).filter((x) => x && !x.startsWith('#'))
}
function dedup(arr) {
  return [...new Set(arr)]
}

export const useProxyStore = defineStore('proxy', () => {
  let saved = []
  try { saved = JSON.parse(localStorage.getItem(KEY) || '[]') } catch (_) { saved = [] }

  const list = ref(Array.isArray(saved) ? saved : [])
  const text = computed(() => list.value.join('\n'))
  const count = computed(() => list.value.length)
  const syncState = ref('loading')
  let initialized = false
  let applyingRemote = false
  let revision = 0
  let saveTimer
  let saveQueue = Promise.resolve()

  function storeLocally(value) {
    try { localStorage.setItem(KEY, JSON.stringify(value)) } catch (_) {}
  }

  function queueServerSave() {
    if (!initialized || applyingRemote) return
    clearTimeout(saveTimer)
    syncState.value = 'saving'
    saveTimer = setTimeout(() => {
      saveQueue = saveQueue.then(async () => {
        const snapshot = [...list.value]
        const savedRevision = revision
        try {
          await saveProxyPool(snapshot)
          if (savedRevision === revision) syncState.value = 'saved'
        } catch (_) {
          if (savedRevision === revision) syncState.value = 'local-only'
        }
      })
    }, 350)
  }

  watch(list, (value) => {
    storeLocally(value)
    if (!applyingRemote) {
      revision += 1
      queueServerSave()
    }
  }, { deep: true, flush: 'sync' })

  async function loadFromServer() {
    const initialRevision = revision
    try {
      const remote = await getProxyPool()
      if (revision !== initialRevision) {
        initialized = true
        queueServerSave()
        return
      }
      if (remote.configured) {
        applyingRemote = true
        list.value = Array.isArray(remote.proxies) ? remote.proxies : []
        applyingRemote = false
        storeLocally(list.value)
      } else if (list.value.length) {
        // One-time migration for an existing browser's local pool on first VPS use.
        await saveProxyPool([...list.value])
      }
      initialized = true
      syncState.value = 'saved'
      if (remote.configured === false && revision !== initialRevision) queueServerSave()
    } catch (_) {
      applyingRemote = false
      initialized = true
      syncState.value = 'local-only'
    }
  }
  void loadFromServer()

  function setFromText(s) {
    const parsed = parseLines(s)
    const unique = dedup(parsed)
    list.value = unique
    return { total: parsed.length, kept: unique.length, duplicated: parsed.length - unique.length }
  }

  function append(s) {
    const merged = dedup([...list.value, ...parseLines(s)])
    const added = merged.length - list.value.length
    list.value = merged
    return { added }
  }

  function remove(proxy) {
    list.value = list.value.filter((x) => x !== proxy)
  }
  function clear() {
    list.value = []
  }

  return { list, text, count, syncState, setFromText, append, remove, clear }
})

/**
 * 兼容：
 * 1) [scheme://][user:pass@]host:port
 * 2) host:port:user:pass（muse-protocol 四段格式）
 */
export function isValidProxy(p) {
  const s = String(p || '').trim()
  if (!s) return false
  if (/^((socks5h?|socks4|https?):\/\/)?[^:\s]+:\d+$/i.test(s)) return true
  if (/^((socks5h?|socks4|https?):\/\/)?\S+@[^:\s]+:\d+$/i.test(s)) return true
  const parts = s.split(':')
  if (parts.length === 4 && /^\d+$/.test(parts[1])) return true
  return false
}

export function proxyScheme(p) {
  const s = String(p || '').trim()
  const m = /^(socks5h?|socks4|https?):\/\//i.exec(s)
  if (m) return m[1].toLowerCase()
  const parts = s.split(':')
  if (parts.length === 4 && /^\d+$/.test(parts[1])) return 'http(四段认证)'
  return 'http(默认)'
}
