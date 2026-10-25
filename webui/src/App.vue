<script setup lang="ts">
import { NConfigProvider, NGlobalStyle, darkTheme, enUS, zhCN } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { fetchTools, isDark, onContext as onBridgeContext, ready, type ToolInfo } from './bridge'
import ToolDetail from './components/ToolDetail.vue'
import ToolList from './components/ToolList.vue'
import TestBench from './components/TestBench.vue'
import ThemeShell from './components/ThemeShell.vue'
import { useI18n } from './i18n'

const { t, locale } = useI18n()

const tools = ref<ToolInfo[]>([])
const selectedName = ref<string | null>(null)
const dark = ref(isDark())

const selected = computed(() => tools.value.find((tool) => tool.name === selectedName.value) ?? null)
const naiveLocale = computed(() => (locale.value.toLowerCase().startsWith('zh') ? zhCN : enUS))
const countText = computed(() =>
  t('count', '{total} 个工具 · {enabled} 个已启用')
    .replace('{total}', String(tools.value.length))
    .replace('{enabled}', String(tools.value.filter((tool) => tool.active).length)),
)

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

function select(name: string): void {
  selectedName.value = name
}
</script>

<template>
  <NConfigProvider :theme="dark ? darkTheme : null" :locale="naiveLocale">
    <NGlobalStyle />
    <ThemeShell>
      <header class="tk-top">
        <span class="tk-title" id="heading">{{ t('heading', 'Agent Toolkit') }}</span>
        <span class="tk-count" id="tool-count">{{ countText }}</span>
      </header>

      <main class="tk-main">
        <ToolList :tools="tools" :selected="selectedName" @select="select" />

        <section class="tk-content">
          <ToolDetail :tool="selected" />
          <TestBench :tool="selected" />
        </section>
      </main>
    </ThemeShell>
  </NConfigProvider>
</template>
