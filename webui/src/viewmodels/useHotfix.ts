import { computed, reactive, ref } from 'vue'
import {
  applyHotfixSelection,
  getHotfixStatus,
  refreshHotfix,
  updateHotfix,
  type HotfixPatch,
  type HotfixStatus,
} from '../bridge'
import { useI18n } from '../i18n'

export function useHotfix() {
  const { t } = useI18n('views.hotfix')

  const state = reactive({
    status: null as HotfixStatus | null,
    draft: {} as Record<string, boolean>,
    loading: true,
    saving: false,
    refreshing: false,
    updating: false,
    error: '',
    patches: [] as HotfixPatch[],
    applied: 0,
    pending: 0,
  })

  function refreshDerived(): void {
    const patches = state.status?.patches ?? []
    state.patches = patches
    state.applied = patches.filter((patch) => patch.state === 'applied').length
    state.pending = patches.filter((patch) => state.draft[patch.name] !== patch.selected).length
  }

  function sync(next: HotfixStatus): void {
    state.status = next
    state.draft = Object.fromEntries(next.patches.map((patch) => [patch.name, patch.selected]))
    state.error = next.error || ''
    refreshDerived()
  }

  async function load(): Promise<void> {
    try {
      sync(await getHotfixStatus())
    } catch {
      state.error = t('request_failed', '请求失败')
    } finally {
      state.loading = false
    }
  }

  async function save(): Promise<void> {
    if (!state.pending || state.saving) {
      return
    }
    state.saving = true
    try {
      const selected = state.patches
        .filter((patch) => state.draft[patch.name])
        .map((patch) => patch.name)
      sync(await applyHotfixSelection(selected))
    } catch {
      state.error = t('request_failed', '请求失败')
    } finally {
      state.saving = false
    }
  }

  async function refresh(): Promise<void> {
    if (state.refreshing) {
      return
    }
    state.refreshing = true
    try {
      sync(await refreshHotfix())
    } catch {
      state.error = t('request_failed', '请求失败')
    } finally {
      state.refreshing = false
    }
  }

  function discard(): void {
    if (state.status) {
      sync(state.status)
    }
  }

  async function update(name: string): Promise<void> {
    if (state.updating) {
      return
    }
    state.updating = true
    try {
      sync(await updateHotfix([name]))
    } catch {
      state.error = t('request_failed', '请求失败')
    } finally {
      state.updating = false
    }
  }

  function toggle(name: string): void {
    state.draft = { ...state.draft, [name]: !state.draft[name] }
    refreshDerived()
  }

  return reactive({ state, load, save, refresh, discard, toggle, update })
}

export type HotfixViewModel = ReturnType<typeof useHotfix>
