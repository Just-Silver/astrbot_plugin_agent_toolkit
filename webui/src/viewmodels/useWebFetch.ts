import { computed, reactive, type ComputedRef } from 'vue'
import { copyText, runFetch, type FetchResult, type ToolInfo } from '../bridge'
import { useI18n } from '../i18n'

export function useWebFetch(tool: ComputedRef<ToolInfo | null>) {
  const { t } = useI18n()

  const state = reactive({
    url: '',
    maxChars: 8000 as number | null,
    timeout: 30 as number | null,
    loading: false,
    result: null as FetchResult | null,
    error: '',
    copied: false,
  })

  const disabled = computed(
    () => !tool.value || state.loading || !state.url.trim(),
  )

  async function submit(): Promise<void> {
    if (disabled.value) {
      return
    }
    state.loading = true
    state.error = ''
    try {
      state.result = await runFetch({
        url: state.url.trim(),
        max_chars: state.maxChars ?? 8000,
        timeout: state.timeout ?? 30,
      })
    } catch {
      state.error = t('request_failed', '请求失败')
    } finally {
      state.loading = false
    }
  }

  async function copy(): Promise<void> {
    if (!state.result?.output) {
      return
    }
    await copyText(state.result.output)
    state.copied = true
    window.setTimeout(() => {
      state.copied = false
    }, 1500)
  }

  return reactive({ state, disabled, submit, copy })
}

export type WebFetchViewModel = ReturnType<typeof useWebFetch>
