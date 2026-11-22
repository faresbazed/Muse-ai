<script setup>
// 内容区底部悬浮操作条（Ant Pro FooterToolbar 风格）：滚到哪都能保存。
</script>

<template>
  <div class="footer-toolbar">
    <div class="ft-left"><slot name="left" /></div>
    <div class="ft-right"><slot /></div>
  </div>
</template>

<style scoped>
.footer-toolbar {
  position: sticky;
  bottom: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 16px -4px -4px;
  padding: 12px 20px;
  background: var(--app-header-bg);
  border: 1px solid var(--app-border);
  border-radius: 8px;
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.06);
}
.ft-left { color: var(--el-text-color-secondary); font-size: 12px; }
.ft-right { display: flex; align-items: center; gap: 10px; margin-left: auto; }
</style>

<style scoped>
@media (max-width: 768px) {
  .footer-toolbar { flex-wrap: wrap; padding: 12px; padding-bottom: max(12px, env(safe-area-inset-bottom)); margin-inline: 0; }
  .ft-left { width: 100%; overflow-wrap: anywhere; }
  .ft-right { width: 100%; flex-wrap: wrap; margin: 0; }
  .ft-right :deep(.el-button) { flex: 1 1 auto; }
}
</style>
