import test from 'node:test'
import assert from 'node:assert/strict'
import { AR, translateUiText } from '../src/ui-translations.js'

test('Arabic labels are concise and distinguish activation from authentication tokens', () => {
  assert.equal(translateUiText('全自动批量'), 'التسجيل الجماعي')
  assert.equal(translateUiText('令牌数'), 'عدد رموز المصادقة')
  assert.equal(translateUiText('跳过兑换（仅注册激活）'), 'التسجيل فقط دون رمز دعوة')
  assert.ok(Object.values(AR).every(value => !/[\u3400-\u9fff]/.test(value)))
})
test('Dynamic counts, confirmations and provider labels are translated', () => {
  for (const value of [
    '删除选中 (12)', '重置选中 (3)', '从邀请码池取码（余 30 次）',
    '导入格式 2 段', '当前邮箱来源：iCloud 中转 / OTP 链接池',
    '确定删除选中的 4 个号？(不可恢复)',
    'CF Worker 临时邮箱 无需配置全局密钥，请前往「导入邮箱」页一键同步 4173 或粘贴邮箱列表。',
  ]) assert.ok(!/[\u3400-\u9fff]/.test(translateUiText(value)), value)
})
test('Language selection preserves Chinese and raw identifiers', () => {
  assert.equal(translateUiText('删除选中 (12)', 'zh-CN'), '删除选中 (12)')
  for (const value of ['fixture@example.com', 'hatch_sess', 'fixture-token-123', 'https://example.com/otp']) {
    assert.equal(translateUiText(value), value)
  }
  assert.equal(translateUiText('  保存配置  '), '  حفظ الإعدادات  ')
})
