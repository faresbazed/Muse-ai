import http from './request'

export const getProxyPool = () => http.get('/api/settings/proxy')
export const saveProxyPool = (proxies) => http.post('/api/settings/proxy', { proxies })

// 代理连通性测试（后端并发测试，可能耗时，单独放宽超时到 3 分钟）
export const testProxies = (proxies, timeout = 8) =>
  http.post('/api/proxy/test', { proxies, timeout }, { timeout: 180000 })
