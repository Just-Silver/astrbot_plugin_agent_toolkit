import { ref } from 'vue'
import { locale as bridgeLocale, onContext, tFor } from './bridge'

const current = ref(bridgeLocale())

onContext(() => {
  current.value = bridgeLocale()
})

export function useI18n(prefix = 'views.toolkit') {
  const t = (key: string, fallback: string): string => {
    // Touch the ref so templates re-render when the dashboard language changes.
    void current.value
    return tFor(prefix, key, fallback)
  }
  return { t, locale: current }
}
