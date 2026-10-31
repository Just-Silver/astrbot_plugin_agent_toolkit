<script setup lang="ts">
import { NButton, NInput, NInputNumber } from 'naive-ui'
import type { ToolInfo } from '../bridge'
import { useI18n } from '../i18n'
import type { WebFetchViewModel } from '../viewmodels/useWebFetch'

defineProps<{ tool: ToolInfo | null; vm: WebFetchViewModel }>()
const { t } = useI18n()
</script>

<template>
  <div v-if="tool" class="tk-bench">
    <div class="tk-row">
      <NInput
        v-model:value="vm.state.url"
        placeholder="https://example.com"
        :disabled="vm.state.loading"
        @keyup.enter="vm.submit"
      />
      <NButton type="primary" :loading="vm.state.loading" :disabled="vm.disabled" @click="vm.submit">
        {{ vm.state.loading ? t('fetching', '抓取中…') : t('fetch', '抓取') }}
      </NButton>
    </div>

    <div class="tk-adv">
      <label class="tk-field">
        <span>{{ t('max_chars', '字符上限') }}</span>
        <NInputNumber v-model:value="vm.state.maxChars" :min="1000" :max="50000" :step="1000" size="small" />
      </label>
      <label class="tk-field">
        <span>{{ t('timeout', '超时') }}</span>
        <NInputNumber v-model:value="vm.state.timeout" :min="5" :max="120" :step="5" size="small" />
        <span>{{ t('seconds', '秒') }}</span>
      </label>
      <span class="tk-fade">{{ t('only_once', '仅本次测试生效') }}</span>
    </div>

    <div v-if="vm.state.result" class="tk-meta">
      <span>{{ vm.state.result.elapsed_ms }} ms</span>
      <span>{{ vm.state.result.chars }} {{ t('chars', '字符') }}</span>
      <span>{{ vm.state.result.truncated ? t('truncated', '已截断') : t('not_truncated', '未截断') }}</span>
      <span>{{ vm.state.result.final_url || '—' }}</span>
    </div>

    <p v-if="vm.state.error" class="tk-error">{{ vm.state.error }}</p>

    <pre v-if="vm.state.result" class="tk-out" :class="{ error: !vm.state.result.ok }">{{ vm.state.result.output }}</pre>

    <div v-if="vm.state.result" class="tk-actions">
      <NButton size="small" quaternary @click="vm.copy">
        {{ vm.state.copied ? t('copied', '已复制') : t('copy', '复制') }}
      </NButton>
    </div>
  </div>
</template>
