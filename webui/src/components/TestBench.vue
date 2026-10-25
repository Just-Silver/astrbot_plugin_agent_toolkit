<script setup lang="ts">
import { NButton, NInput, NInputNumber } from 'naive-ui'
import { computed, ref } from 'vue'
import { copyText, runFetch, type FetchResult, type ToolInfo } from '../bridge'
import { useI18n } from '../i18n'

const props = defineProps<{ tool: ToolInfo | null }>()
const { t } = useI18n()

const url = ref('')
const maxChars = ref<number | null>(8000)
const timeout = ref<number | null>(30)
const loading = ref(false)
const result = ref<FetchResult | null>(null)
const error = ref('')
const copied = ref(false)

const disabled = computed(() => !props.tool || loading.value || !url.value.trim())

async function submit(): Promise<void> {
  if (disabled.value) {
    return
  }
  loading.value = true
  error.value = ''
  try {
    result.value = await runFetch({
      url: url.value.trim(),
      max_chars: maxChars.value ?? 8000,
      timeout: timeout.value ?? 30,
    })
  } catch {
    error.value = t('request_failed', '请求失败')
  } finally {
    loading.value = false
  }
}

async function copy(): Promise<void> {
  if (!result.value?.output) {
    return
  }
  await copyText(result.value.output)
  copied.value = true
  window.setTimeout(() => {
    copied.value = false
  }, 1500)
}
</script>

<template>
  <div v-if="tool" class="tk-bench">
    <div class="tk-row">
      <NInput
        v-model:value="url"
        placeholder="https://example.com"
        :disabled="loading"
        @keyup.enter="submit"
      />
      <NButton type="primary" :loading="loading" :disabled="disabled" @click="submit">
        {{ loading ? t('fetching', '抓取中…') : t('fetch', '抓取') }}
      </NButton>
    </div>

    <div class="tk-adv">
      <label class="tk-field">
        <span>{{ t('max_chars', '字符上限') }}</span>
        <NInputNumber v-model:value="maxChars" :min="1000" :max="50000" :step="1000" size="small" />
      </label>
      <label class="tk-field">
        <span>{{ t('timeout', '超时') }}</span>
        <NInputNumber v-model:value="timeout" :min="5" :max="120" :step="5" size="small" />
        <span>{{ t('seconds', '秒') }}</span>
      </label>
      <span class="tk-fade">{{ t('only_once', '仅本次测试生效') }}</span>
    </div>

    <div v-if="result" class="tk-meta">
      <span>{{ result.elapsed_ms }} ms</span>
      <span>{{ result.chars }} {{ t('chars', '字符') }}</span>
      <span>{{ result.truncated ? t('truncated', '已截断') : t('not_truncated', '未截断') }}</span>
      <span>{{ result.final_url || '—' }}</span>
    </div>

    <p v-if="error" class="tk-error">{{ error }}</p>

    <pre v-if="result" class="tk-out" :class="{ error: !result.ok }">{{ result.output }}</pre>

    <div v-if="result" class="tk-actions">
      <NButton size="small" quaternary @click="copy">
        {{ copied ? t('copied', '已复制') : t('copy', '复制') }}
      </NButton>
    </div>
  </div>
</template>
