<script setup lang="ts">
import { NAlert, NButton, NSpin } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import {
  applyHotfixSelection,
  getHotfixStatus,
  refreshHotfix,
  type HotfixStatus,
} from '../bridge'
import { useI18n } from '../i18n'
import HotfixList from './HotfixList.vue'

const emit = defineEmits<{ (event: 'status', value: HotfixStatus | null): void }>()
const { t } = useI18n('views.hotfix')
const status = ref<HotfixStatus | null>(null)
const draft = ref<Record<string, boolean>>({})
const loading = ref(true)
const saving = ref(false)
const refreshing = ref(false)
const error = ref('')

const patches = computed(() => status.value?.patches ?? [])
const enabled = computed(() => status.value?.enabled ?? false)
const applied = computed(() => patches.value.filter((patch) => patch.state === 'applied').length)
const pending = computed(
  () => patches.value.filter((patch) => draft.value[patch.name] !== patch.selected).length,
)

function sync(next: HotfixStatus): void {
  status.value = next
  draft.value = Object.fromEntries(next.patches.map((patch) => [patch.name, patch.selected]))
  error.value = next.error || ''
  emit('status', next)
}

async function load(): Promise<void> {
  try {
    sync(await getHotfixStatus())
  } catch {
    error.value = t('request_failed', '请求失败')
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!pending.value || saving.value) {
    return
  }
  saving.value = true
  try {
    const selected = patches.value
      .filter((patch) => draft.value[patch.name])
      .map((patch) => patch.name)
    sync(await applyHotfixSelection(selected))
  } catch {
    error.value = t('request_failed', '请求失败')
  } finally {
    saving.value = false
  }
}

async function refresh(): Promise<void> {
  if (refreshing.value) {
    return
  }
  refreshing.value = true
  try {
    sync(await refreshHotfix())
  } catch {
    error.value = t('request_failed', '请求失败')
  } finally {
    refreshing.value = false
  }
}

function discard(): void {
  if (status.value) {
    sync(status.value)
  }
}

function toggle(name: string): void {
  draft.value = { ...draft.value, [name]: !draft.value[name] }
}

function formatTime(value: string): string {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

onMounted(load)
</script>

<template>
  <div class="tk-head">
    <span class="tk-name">{{ t('heading', '热补丁') }}</span>
    <span class="tk-count">
      {{ t('summary', '{total} 个补丁 · {applied} 个已应用 · {pending} 个待应用')
        .replace('{total}', String(patches.length))
        .replace('{applied}', String(applied))
        .replace('{pending}', String(pending)) }}
    </span>
    <span class="hf-spacer"></span>
    <NButton size="small" :loading="refreshing" :disabled="!enabled" @click="refresh">
      {{ refreshing ? t('refreshing', '刷新中…') : t('refresh', '刷新') }}
    </NButton>
  </div>

  <div class="hf-source">
    <span>{{ status?.repo || t('no_repo', '未配置仓库') }}</span>
    <span v-if="status?.ref">· {{ status.ref }}</span>
    <span v-if="status?.commit">· {{ status.commit }}</span>
    <span v-if="status?.updated_at">· {{ formatTime(status.updated_at) }}</span>
  </div>

  <NAlert v-if="status && !enabled" type="warning" :bordered="false" class="hf-alert">
    {{ t('not_enabled', '热补丁未启用，请在插件配置页开启') }}
  </NAlert>
  <NAlert v-if="error" type="error" :bordered="false" closable class="hf-alert" @close="error = ''">
    {{ error }}
  </NAlert>

  <NSpin :show="loading || saving">
    <div class="hf-panel">
      <HotfixList :patches="patches" :draft="draft" :disabled="!enabled || saving" @toggle="toggle" />
    </div>
  </NSpin>

  <footer v-if="pending" class="hf-actions">
    <NButton size="small" :disabled="saving" @click="discard">{{ t('discard', '放弃') }}</NButton>
    <NButton size="small" type="primary" :loading="saving" @click="save">
      {{ t('apply_count', '应用更改（{count}）').replace('{count}', String(pending)) }}
    </NButton>
  </footer>
</template>
