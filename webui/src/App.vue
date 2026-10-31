<script setup lang="ts">
import { NConfigProvider, NGlobalStyle, darkTheme, enUS, zhCN } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import {
  fetchTools,
  isDark,
  onContext as onBridgeContext,
  ready,
  type HotfixStatus,
  type ToolInfo,
} from './bridge'
import HotfixPanel from './components/HotfixPanel.vue'
import WebFetchPanel from './components/WebFetchPanel.vue'
import ToolList from './components/ToolList.vue'
import ThemeShell from './components/ThemeShell.vue'
import { useI18n } from './i18n'

const { t, locale } = useI18n()

const tools = ref<ToolInfo[]>([])
const selectedName = ref<string | null>(null)
const mode = ref<'tool' | 'hotfix'>('tool')
const hotfixStatus = ref<HotfixStatus | null>(null)
const dark = ref(isDark())

const selected = computed(() => tools.value.find((tool) => tool.name === selectedName.value) ?? null)
const naiveLocale = computed(() => (locale.value.toLowerCase().startsWith('zh') ? zhCN : enUS))
const hotfixTotal = computed(() => hotfixStatus.value?.patches.length ?? 0)
const hotfixApplied = computed(
  () => hotfixStatus.value?.patches.filter((patch) => patch.state === 'applied').length ?? 0,
)

const countText = computed(() => {
  if (mode.value === 'hotfix') {
    return t('hotfix_count', '{total} 个补丁 · {applied} 个已应用')
      .replace('{total}', String(hotfixTotal.value))
      .replace('{applied}', String(hotfixApplied.value))
  }
  return t('count', '{total} 个工具 · {enabled} 个已启用')
    .replace('{total}', String(tools.value.length))
    .replace('{enabled}', String(tools.value.filter((tool) => tool.active).length))
})

const title = computed(() => (mode.value === 'hotfix' ? t('hotfix_heading', '热补丁') : t('heading', 'Agent Toolkit')))

onMounted(async () => {
  await ready()
  dark.value = isDark()
  try {
    tools.value = await fetchTools()
  } catch {
    tools.value = []
  }
  selectedName.value = tools.value[0]?.name ?? null
  onBridgeContext(() => {
    dark.value = isDark()
  })
})

function selectTool(name: string): void {
  mode.value = 'tool'
  selectedName.value = name
}

function selectHotfix(): void {
  mode.value = 'hotfix'
}
</script>

<template>
  <NConfigProvider :theme="dark ? darkTheme : null" :locale="naiveLocale">
    <NGlobalStyle />
    <ThemeShell>
      <header class="tk-top">
        <span class="tk-title" id="heading">{{ title }}</span>
        <span class="tk-count" id="tool-count">{{ countText }}</span>
      </header>

      <main class="tk-main">
        <aside class="tk-side">
          <div class="tk-side-label">{{ t('tools', '工具') }}</div>
          <ToolList
            :tools="tools"
            :selected="mode === 'tool' ? selectedName : null"
            @select="selectTool"
          />

          <div class="tk-side-label">{{ t('modules', '模块') }}</div>
          <button
            type="button"
            class="tk-item"
            :class="{ on: mode === 'hotfix' }"
            @click="selectHotfix"
          >
            <span class="dot" :class="{ off: !hotfixApplied }"></span>
            <span class="tk-item-name">{{ t('hotfix_module', '热补丁') }}</span>
            <span v-if="hotfixTotal" class="tk-item-count">{{ hotfixApplied }}/{{ hotfixTotal }}</span>
          </button>
        </aside>

        <section class="tk-content">
          <template v-if="mode === 'tool'">
            <WebFetchPanel :tool="selected" />
          </template>
          <HotfixPanel v-else @status="hotfixStatus = $event" />
        </section>
      </main>
    </ThemeShell>
  </NConfigProvider>
</template>
