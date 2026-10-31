<script setup lang="ts">
import { NConfigProvider, NGlobalStyle, darkTheme, enUS, zhCN } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { isDark, onContext as onBridgeContext, ready } from './bridge'
import HotfixPanel from './components/HotfixPanel.vue'
import WebFetchPanel from './components/WebFetchPanel.vue'
import ToolList from './components/ToolList.vue'
import ThemeShell from './components/ThemeShell.vue'
import { useI18n } from './i18n'
import { useHotfix } from './viewmodels/useHotfix'
import { useTools } from './viewmodels/useTools'
import { useWebFetch } from './viewmodels/useWebFetch'

const { t, locale } = useI18n()

const mode = ref<'tool' | 'hotfix'>('tool')
const dark = ref(isDark())

const tools = useTools()
const hotfix = useHotfix()
const webFetch = useWebFetch(computed(() => tools.selectedTool))

const naiveLocale = computed(() => (locale.value.toLowerCase().startsWith('zh') ? zhCN : enUS))

const countText = computed(() => {
  if (mode.value === 'hotfix') {
    return t('hotfix_count', '{total} 个补丁 · {applied} 个已应用')
      .replace('{total}', String(hotfix.state.patches.length))
      .replace('{applied}', String(hotfix.state.applied))
  }
  return t('count', '{total} 个工具 · {enabled} 个已启用')
    .replace('{total}', String(tools.state.tools.length))
    .replace(
      '{enabled}',
      String(tools.state.tools.filter((tool) => tool.active).length),
    )
})

const title = computed(() =>
  mode.value === 'hotfix' ? t('hotfix_heading', '热补丁') : t('heading', 'Agent Toolkit'),
)

onMounted(async () => {
  await ready()
  dark.value = isDark()
  await tools.load()
  await hotfix.load()
  onBridgeContext(() => {
    dark.value = isDark()
  })
})

function selectTool(name: string): void {
  mode.value = 'tool'
  tools.select(name)
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
            :tools="tools.state.tools"
            :selected="mode === 'tool' ? tools.state.selected : null"
            @select="selectTool"
          />

          <div class="tk-side-label">{{ t('modules', '模块') }}</div>
          <button
            type="button"
            class="tk-item"
            :class="{ on: mode === 'hotfix' }"
            @click="selectHotfix"
          >
            <span class="dot" :class="{ off: !hotfix.state.applied }"></span>
            <span class="tk-item-name">{{ t('hotfix_module', '热补丁') }}</span>
            <span v-if="hotfix.state.patches.length" class="tk-item-count">
              {{ hotfix.state.applied }}/{{ hotfix.state.patches.length }}
            </span>
          </button>
        </aside>

        <section class="tk-content">
          <WebFetchPanel v-if="mode === 'tool'" :tool="tools.selectedTool" :vm="webFetch" />
          <HotfixPanel v-else :vm="hotfix" />
        </section>
      </main>
    </ThemeShell>
  </NConfigProvider>
</template>
