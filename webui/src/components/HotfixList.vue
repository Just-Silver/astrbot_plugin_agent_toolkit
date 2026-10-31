<script setup lang="ts">
import { NSwitch, NTag } from 'naive-ui'
import { ref } from 'vue'
import type { HotfixPatch } from '../bridge'
import { useI18n } from '../i18n'

const props = defineProps<{
  patches: HotfixPatch[]
  draft: Record<string, boolean>
  disabled: boolean
}>()
const emit = defineEmits<{ (event: 'toggle', name: string): void }>()
const { t } = useI18n('views.hotfix')
const expanded = ref<Set<string>>(new Set())

function toggleRow(name: string): void {
  const next = new Set(expanded.value)
  if (next.has(name)) {
    next.delete(name)
  } else {
    next.add(name)
  }
  expanded.value = next
}

function isPending(patch: HotfixPatch): boolean {
  return props.draft[patch.name] !== patch.selected
}

function stateLabel(patch: HotfixPatch): string {
  if (isPending(patch)) {
    return t('status_pending', '待应用')
  }
  switch (patch.state) {
    case 'applied':
      return t('status_applied', '已应用')
    case 'incompatible':
      return t('status_incompatible', '版本不匹配')
    case 'failed':
      return t('status_failed', '加载失败')
    default:
      return t('status_disabled', '未启用')
  }
}

function stateType(patch: HotfixPatch): 'success' | 'warning' | 'error' | 'default' {
  if (isPending(patch)) {
    return 'warning'
  }
  switch (patch.state) {
    case 'applied':
      return 'success'
    case 'incompatible':
      return 'warning'
    case 'failed':
      return 'error'
    default:
      return 'default'
  }
}

function stateHint(patch: HotfixPatch): string {
  if (isPending(patch) || patch.state === 'applied') {
    return ''
  }
  return patch.reason
}

function formatTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}
</script>

<template>
  <div class="hf-table">
    <div class="hf-row hf-head">
      <span class="hf-col-name">{{ t('col_patch', '补丁') }}</span>
      <span class="hf-col-ver">{{ t('col_version', '适用版本') }}</span>
      <span class="hf-col-state">{{ t('col_state', '状态') }}</span>
      <span class="hf-col-switch">{{ t('col_enabled', '启用') }}</span>
    </div>

    <div v-if="!patches.length" class="hf-empty">{{ t('empty', '仓库里没有补丁') }}</div>

    <div v-for="patch in patches" :key="patch.name" class="hf-item">
      <div class="hf-row hf-main" @click="toggleRow(patch.name)">
        <span class="hf-col-name">
          <span class="hf-caret">{{ expanded.has(patch.name) ? '▾' : '▸' }}</span>
          <span class="hf-name">{{ patch.name }}</span>
          <span v-if="patch.description" class="hf-desc">{{ patch.description }}</span>
        </span>
        <span class="hf-col-ver">{{ patch.astrbot || '*' }}</span>
        <span class="hf-col-state">
          <NTag size="small" :type="stateType(patch)" round>{{ stateLabel(patch) }}</NTag>
          <span v-if="stateHint(patch)" class="hf-hint" :class="patch.state">{{ stateHint(patch) }}</span>
        </span>
        <span class="hf-col-switch" @click.stop>
          <NSwitch
            size="small"
            :value="draft[patch.name]"
            :disabled="disabled"
            @update:value="emit('toggle', patch.name)"
          />
        </span>
      </div>

      <div v-if="expanded.has(patch.name)" class="hf-detail">
        <div v-for="target in patch.targets" :key="target" class="hf-detail-line">
          <span class="hf-label">{{ t('targets', '目标') }}：</span>{{ target }}
        </div>
        <div class="hf-detail-line">
          <span class="hf-label">{{ t('file', '文件') }}：</span>{{ patch.file }}
        </div>
        <div v-if="patch.applied_at" class="hf-detail-line">
          <span class="hf-label">{{ t('applied_at', '上次应用') }}：</span>{{ formatTime(patch.applied_at) }}
        </div>
        <div v-if="patch.reason && !isPending(patch)" class="hf-detail-line hf-reason">
          {{ patch.reason }}
        </div>
      </div>
    </div>
  </div>
</template>
