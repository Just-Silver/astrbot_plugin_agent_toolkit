<script setup lang="ts">
import type { ToolInfo } from '../bridge'
import type { WebFetchViewModel } from '../viewmodels/useWebFetch'
import TestBench from './TestBench.vue'
import ToolDetail from './ToolDetail.vue'

defineProps<{ tool: ToolInfo | null; vm: WebFetchViewModel }>()
</script>

<template>
  <ToolDetail :tool="tool" />
  <TestBench :tool="tool" :vm="vm" />
</template>
