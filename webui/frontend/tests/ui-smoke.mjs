// Offline browser checks. No user accounts or external services are contacted.
import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '../..')
const output = path.resolve(here, '../test-results')
fs.mkdirSync(output, { recursive: true })
const providers = JSON.parse(fs.readFileSync(path.join(here, 'fixtures/providers.json'), 'utf8'))
const routes = ['/', '/pool', '/import', '/invites', '/proxy', '/register', '/auto', '/registered', '/runs', '/settings/mail']
const cases = routes.flatMap((route, index) => [
  [`phone-ar-${index}`, 390, 844, 'ar', route],
  [`desktop-ar-${index}`, 1440, 1000, 'ar', route],
])
cases.push(['narrow-ar', 320, 740, 'ar', '/settings/mail'], ['tablet-ar', 820, 1180, 'ar', '/'], ['desktop-zh', 1440, 1000, 'zh-CN', '/'])
const summary = { stats: { total: 1, available: 1, in_use: 0, done: 0, failed: 0 }, invites: { total: 1, available: 1, remaining_uses: 30 }, registered: { total: 1, redeemed: 1, own_codes: 1 } }
const account = { email: 'fixture@example.com', account_id: 'fixture-account', status: 'activated', token_count: 1, st_len: 24, own_code: '', created_at: 1700000000 }
const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXECUTABLE_PATH ? { executablePath: process.env.BROWSER_EXECUTABLE_PATH } : {}) })
const results = []

async function settle(page, width) {
  await page.locator('.page').waitFor({ state: 'visible' })
  await page.locator('#nprogress').waitFor({ state: 'hidden' })
  if (width <= 768) await page.locator('.sidebar').waitFor({ state: 'hidden' })
}
async function inspect(page, language) {
  const state = await page.evaluate(() => {
    const untranslated = []
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    let node
    while ((node = walker.nextNode())) {
      const parent = node.parentElement
      if (!/[\u3400-\u9fff]/.test(node.nodeValue) || !parent || parent.closest('script,style,pre,code,.mono,.log-box,textarea')) continue
      const rect = parent.getBoundingClientRect()
      if (rect.width && rect.height && getComputedStyle(parent).visibility !== 'hidden' && rect.left < innerWidth && rect.right > 0) untranslated.push(node.nodeValue.trim())
    }
    return { viewport: innerWidth, width: document.body.scrollWidth, untranslated: [...new Set(untranslated)] }
  })
  assert.ok(state.width <= state.viewport + 1, `Page overflow: ${JSON.stringify(state)}`)
  if (language === 'ar') assert.deepEqual(state.untranslated, [], 'Untranslated UI labels')
  return state
}

try {
  for (const [name, width, height, language, hash] of cases.filter(value => !process.env.UI_CASE || value[0] === process.env.UI_CASE)) {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 })
    const errors = []
    const writes = []
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(language => localStorage.setItem('muse_ui_locale_v1', language), language)
    await page.route('**/*', async route => {
      const request = route.request()
      const url = new URL(request.url())
      if (url.origin !== 'http://panel.test') return route.abort()
      if (url.pathname.startsWith('/api/')) {
        if (request.method() !== 'GET') writes.push({ method: request.method(), path: url.pathname })
        let data = { ok: true }
        if (url.pathname === '/api/stats') Object.assign(data, summary)
        else if (url.pathname === '/api/accounts') Object.assign(data, { items: [{ email: account.email, kind: 'icloud_relay', status: 'available' }], total: 1, by_kind: { icloud_relay: { total: 1 } } })
        else if (url.pathname === '/api/registered') Object.assign(data, { items: [account], total: 1, summary: summary.registered })
        else if (url.pathname === '/api/registered/export/formats') data.formats = []
        else if (url.pathname.startsWith('/api/registered/')) data.data = { ...account, session_token: 'fixture-session-not-a-secret' }
        else if (url.pathname === '/api/mail/providers') Object.assign(data, { current: 'icloud_relay', providers })
        else if (url.pathname === '/api/settings/mail') data.config = { mail_source: 'icloud_relay' }
        else if (url.pathname === '/api/settings/proxy') Object.assign(data, { configured: true, proxies: [] })
        else if (url.pathname.endsWith('/stream')) return route.fulfill({ contentType: 'text/event-stream', body: 'event: state\ndata: {"state":"stopped"}\n\n' })
        else Object.assign(data, { items: [], total: 0, stats: {}, summary: {} })
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) })
      }
      let file = path.join(root, url.pathname)
      if (url.pathname === '/' || url.pathname === '/static/') file = path.join(root, 'static/index.html')
      if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) return route.fulfill({ status: 404, body: 'Not found' })
      const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml' }
      return route.fulfill({ contentType: types[path.extname(file)] || 'application/octet-stream', body: fs.readFileSync(file) })
    })
    await page.goto('http://panel.test/static/#' + hash)
    await settle(page, width)
    const state = await inspect(page, language)
    await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true })
    if (width <= 768) {
      await page.locator('.menu-toggle').click()
      await page.waitForFunction(() => {
        const el = document.querySelector('.sidebar.mobile-open')
        return el && Math.abs(new DOMMatrixReadOnly(getComputedStyle(el).transform).m41) < 0.1
      })
      assert.ok(await page.locator('.nav-backdrop').isVisible())
      await page.screenshot({ path: path.join(output, `${name}-menu.png`) })
      await page.keyboard.press('Escape')
      await page.locator('.sidebar').waitFor({ state: 'hidden' })
      await page.locator('.menu-toggle').click()
      await page.locator('.sidebar .el-menu-item').nth(hash === '/' ? 1 : 0).click()
      await page.locator('.sidebar').waitFor({ state: 'hidden' })
      await page.goto('http://panel.test/static/#' + hash)
      await settle(page, width)
    }
    if (hash === '/register' && language === 'ar') {
      await page.getByText('إظهار الإعدادات المتقدمة', { exact: false }).click()
      await page.getByPlaceholder('اسم العائلة (اتركه فارغاً للعشوائي)').waitFor()
      await inspect(page, language)
      await page.screenshot({ path: path.join(output, `${name}-advanced.png`), fullPage: true })
    }
    if (hash === '/settings/mail' && language === 'ar') {
      await page.locator('.el-radio').filter({ hasText: 'Cloudflare' }).click()
      await page.getByText('نطاق البريد الوارد', { exact: true }).waitFor()
      const checkedProviders = await page.locator('.el-radio input:checked').count()
      assert.equal(checkedProviders, 1, 'Only one provider radio is selected')
      assert.ok(await page.locator('.el-radio').filter({hasText:'Cloudflare'}).locator('input').isChecked())
      await inspect(page, language)
      await page.evaluate(() => window.scrollTo(0, 0))
      await page.screenshot({ path: path.join(output, `${name}-provider.png`), fullPage: true })
    }
    if (hash === '/registered' && language === 'ar') {
      await page.locator('.el-table .el-button').filter({ hasText: 'بيانات الدخول' }).click()
      await page.locator('.el-dialog').filter({ hasText: account.email }).waitFor()
      await inspect(page, language)
      const dialog = page.locator('.el-dialog').filter({ hasText: account.email })
      const box = await dialog.boundingBox()
      assert.ok(box.x >= 0 && box.x + box.width <= width + 1, 'Credential dialog fits viewport')
      await page.waitForFunction(() => {
        const dialog = document.querySelector('.el-overlay-dialog .el-dialog')
        return dialog && getComputedStyle(dialog).opacity === '1' && getComputedStyle(dialog.parentElement.parentElement).opacity === '1' && !document.querySelector('.dialog-fade-enter-active')
      })
      await page.screenshot({ path: path.join(output, `${name}-dialog.png`) })
      await page.keyboard.press('Escape')
      await dialog.waitFor({state:'hidden'})
      await page.getByRole('button', {name:'مسح الكل', exact:true}).click()
      await page.locator('.el-message-box').waitFor()
      await inspect(page, language)
      await page.locator('.el-message-box').getByRole('button', {name:'إلغاء', exact:true}).click()
      await page.locator('.el-message-box').waitFor({state:'hidden'})
    }
    if (hash === '/pool' && language === 'ar') {
      await page.locator('.el-table').getByRole('button', {name:'حذف', exact:true}).click()
      await page.locator('.el-message-box').waitFor()
      await inspect(page, language)
      await page.locator('.el-message-box').getByRole('button', {name:'إلغاء', exact:true}).click()
      await page.locator('.el-message-box').waitFor({state:'hidden'})
    }
    if (hash === '/invites' && language === 'ar') {
      await page.getByRole('button', {name:'تنظيف', exact:true}).click()
      await page.getByRole('menuitem', {name:'مسح جميع رموز الدعوة', exact:true}).click()
      await page.locator('.el-message-box').waitFor()
      await inspect(page, language)
      await page.locator('.el-message-box').getByRole('button', {name:'إلغاء', exact:true}).click()
      await page.locator('.el-message-box').waitFor({state:'hidden'})
    }
    if (name === 'desktop-ar-0') {
      await page.locator('.locale-select').click()
      await page.getByRole('option', { name: 'الصينية المبسطة', exact: true }).click()
      await page.waitForFunction(() => document.documentElement.lang === 'zh-CN' && document.documentElement.dir === 'ltr')
      assert.ok(await page.getByText('快捷准备与管理', { exact: true }).isVisible())
      await page.locator('.locale-select').click()
      await page.getByRole('option', { name: 'العربية', exact: true }).click()
      await page.waitForFunction(() => document.documentElement.lang === 'ar' && document.documentElement.dir === 'rtl')
      await inspect(page, language)
      await page.locator('.search-box input').fill('البريد')
      await page.getByRole('option', { name: /استيراد البريد/ }).waitFor({state:'visible'})
      await page.keyboard.press('Escape')
      await page.locator('.search-box input').fill('')
      await page.getByRole('button', { name: 'الوضع الداكن', exact: true }).click()
      await page.waitForFunction(() => document.documentElement.classList.contains('dark'))
      await page.screenshot({ path: path.join(output, 'desktop-ar-dark.png'), fullPage: true })
      await page.getByRole('button', { name: 'الوضع الفاتح', exact: true }).click()
    }
    assert.deepEqual(errors, [], 'No uncaught browser errors')
    assert.deepEqual(writes, [], 'Inspection must not mutate API state')
    results.push({ name, ...state, errors })
    await page.close()
  }
  fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2))
  console.log(`PASS: ${results.length} viewport/route cases, Arabic labels, menu open/close/navigation, advanced forms, provider fields, and credential dialogs. No API writes.`)
} finally {
  await browser.close()
}
