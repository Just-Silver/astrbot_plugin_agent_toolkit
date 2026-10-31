export interface ToolInfo {
  name: string
  active: boolean
  description: string
  parameters: Record<string, unknown>
}

export interface FetchResult {
  ok: boolean
  output: string
  elapsed_ms: number
  chars: number
  truncated: boolean
  final_url: string
}

export interface HotfixPatch {
  name: string
  description: string
  file: string
  astrbot: string
  targets: string[]
  selected: boolean
  state: 'applied' | 'disabled' | 'incompatible' | 'failed'
  reason: string
  applied_at: string
  latest_version: string
  applied_version: string
  outdated: boolean
  changelog: string[]
}

export interface HotfixStatus {
  enabled: boolean
  repo: string
  ref: string
  commit: string
  updated_at: string
  astrbot_version: string
  patches: HotfixPatch[]
  error: string
}

interface BridgeContext {
  pluginName: string
  displayName: string
  pageName: string
  pageTitle: string
  locale: string
  isDark: boolean
}

interface PluginBridge {
  ready(): Promise<BridgeContext>
  getContext(): BridgeContext | null
  t(key: string, fallback?: string): string
  getLocale(): string
  onContext(handler: () => void): () => void
  apiGet<T>(endpoint: string, params?: Record<string, unknown>): Promise<T>
  apiPost<T>(endpoint: string, body?: unknown): Promise<T>
}

declare global {
  interface Window {
    AstrBotPluginView?: PluginBridge
  }
}

const bridge = window.AstrBotPluginView

export function hasBridge(): boolean {
  return Boolean(bridge)
}

export async function ready(): Promise<BridgeContext | null> {
  return bridge ? await bridge.ready() : null
}

export function isDark(): boolean {
  return Boolean(bridge?.getContext()?.isDark)
}

export function locale(): string {
  return bridge?.getLocale() ?? 'zh-CN'
}

export function tFor(prefix: string, key: string, fallback: string): string {
  if (!bridge) {
    return fallback
  }
  try {
    return bridge.t(`${prefix}.${key}`, fallback) || fallback
  } catch {
    return fallback
  }
}

export function t(key: string, fallback: string): string {
  return tFor('views.toolkit', key, fallback)
}

export function onContext(handler: () => void): void {
  bridge?.onContext(handler)
}

export async function fetchTools(): Promise<ToolInfo[]> {
  if (!bridge) {
    return []
  }
  const data = await bridge.apiGet<{ tools?: ToolInfo[] }>('tools')
  return Array.isArray(data?.tools) ? data.tools : []
}

export async function getHotfixStatus(): Promise<HotfixStatus> {
  if (!bridge) {
    throw new Error('bridge unavailable')
  }
  return await bridge.apiGet<HotfixStatus>('hotfix/status')
}

export async function applyHotfixSelection(selected: string[]): Promise<HotfixStatus> {
  if (!bridge) {
    throw new Error('bridge unavailable')
  }
  return await bridge.apiPost<HotfixStatus>('hotfix/selection', { selected })
}

export async function refreshHotfix(): Promise<HotfixStatus> {
  if (!bridge) {
    throw new Error('bridge unavailable')
  }
  return await bridge.apiPost<HotfixStatus>('hotfix/refresh')
}

export async function updateHotfix(names: string[]): Promise<HotfixStatus> {
  if (!bridge) {
    throw new Error('bridge unavailable')
  }
  return await bridge.apiPost<HotfixStatus>('hotfix/update', { names })
}

export async function runFetch(payload: {
  url: string
  max_chars: number
  timeout: number
}): Promise<FetchResult> {
  if (!bridge) {
    throw new Error('bridge unavailable')
  }
  return await bridge.apiPost<FetchResult>('tools/web_fetch/test', payload)
}

export async function copyText(text: string): Promise<void> {
  try {
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      throw new Error('clipboard unavailable')
    }
    await navigator.clipboard.writeText(text)
    return
  } catch {
    // Insecure origins (plain http) have no async clipboard; fall back to the
    // legacy selection-based copy so the button still works.
  }

  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.top = '-1000px'
  area.style.opacity = '0'
  document.body.append(area)
  area.select()
  try {
    document.execCommand('copy')
  } finally {
    area.remove()
  }
}
