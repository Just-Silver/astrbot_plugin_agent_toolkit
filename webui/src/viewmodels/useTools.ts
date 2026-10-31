import { computed, reactive } from 'vue'
import { fetchTools, type ToolInfo } from '../bridge'

export function useTools() {
  const state = reactive({
    tools: [] as ToolInfo[],
    selected: null as string | null,
  })

  async function load(): Promise<void> {
    try {
      state.tools = await fetchTools()
    } catch {
      state.tools = []
    }
    state.selected = state.tools[0]?.name ?? null
  }

  function select(name: string): void {
    state.selected = name
  }

  const selectedTool = computed(
    () => state.tools.find((tool) => tool.name === state.selected) ?? null,
  )

  return reactive({ state, selectedTool, load, select })
}

export type ToolsViewModel = ReturnType<typeof useTools>
