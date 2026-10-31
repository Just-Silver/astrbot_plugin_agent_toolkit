<script setup lang="ts">
import type { ToolInfo } from '../bridge'
import TestBench from './TestBench.vue'
import ToolDetail from './ToolDetail.vue'

defineProps<{ tool: ToolInfo | null }>()
</script>

<template>
  <ToolDetail :tool="tool" />
  <TestBench :tool="tool" />
</template>
