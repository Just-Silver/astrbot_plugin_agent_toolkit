<script setup lang="ts">
import { NAlert, NButton, NSpin } from 'naive-ui'
import { useI18n } from '../i18n'
import type { HotfixViewModel } from '../viewmodels/useHotfix'
import HotfixList from './HotfixList.vue'

defineProps<{ vm: HotfixViewModel }>()
const { t } = useI18n('views.hotfix')

function formatTime(value: string): string {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}
</script>

<template>
  <div class="tk-head">
    <span class="tk-name">{{ t('heading', '热补丁') }}</span>
    <span class="tk-count">
      {{ t('summary', '{total} 个补丁 · {applied} 个已应用 · {pending} 个待应用')
        .replace('{total}', String(vm.state.patches.length))
        .replace('{applied}', String(vm.state.applied))
        .replace('{pending}', String(vm.state.pending)) }}
    </span>
    <span class="hf-spacer"></span>
    <NButton
      size="small"
      :loading="vm.state.refreshing"
      :disabled="!vm.state.status?.enabled"
      @click="vm.refresh"
    >
      {{ vm.state.refreshing ? t('refreshing', '刷新中…') : t('refresh', '刷新') }}
    </NButton>
  </div>

  <div class="hf-source">
    <span>{{ vm.state.status?.repo || t('no_repo', '未配置仓库') }}</span>
    <span v-if="vm.state.status?.ref">· {{ vm.state.status.ref }}</span>
    <span v-if="vm.state.status?.commit">· {{ vm.state.status.commit }}</span>
    <span v-if="vm.state.status?.updated_at">· {{ formatTime(vm.state.status.updated_at) }}</span>
  </div>

  <NAlert v-if="vm.state.status && !vm.state.status.enabled" type="warning" :bordered="false" class="hf-alert">
    {{ t('not_enabled', '热补丁未启用，请在插件配置页开启') }}
  </NAlert>
  <NAlert
    v-if="vm.state.error"
    type="error"
    :bordered="false"
    closable
    class="hf-alert"
    @close="vm.state.error = ''"
  >
    {{ vm.state.error }}
  </NAlert>

  <NSpin :show="vm.state.loading || vm.state.saving">
    <div class="hf-panel">
      <HotfixList
        :patches="vm.state.patches"
        :draft="vm.state.draft"
        :disabled="!vm.state.status?.enabled || vm.state.saving"
        @toggle="vm.toggle"
      />
    </div>
  </NSpin>

  <footer v-if="vm.state.pending" class="hf-actions">
    <NButton size="small" :disabled="vm.state.saving" @click="vm.discard">
      {{ t('discard', '放弃') }}
    </NButton>
    <NButton size="small" type="primary" :loading="vm.state.saving" @click="vm.save">
      {{ t('apply_count', '应用更改（{count}）').replace('{count}', String(vm.state.pending)) }}
    </NButton>
  </footer>
</template>
