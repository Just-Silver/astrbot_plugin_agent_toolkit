<script setup lang="ts">
import type { ToolInfo } from '../bridge'
import { useI18n } from '../i18n'

defineProps<{ tools: ToolInfo[]; selected: string | null }>()
const emit = defineEmits<{ (event: 'select', name: string): void }>()
const { t } = useI18n()
</script>

<template>
  <div v-if="!tools.length" class="tk-side-empty">{{ t('empty', '当前没有注册任何工具') }}</div>
  <button
    v-for="tool in tools"
    :key="tool.name"
    type="button"
    class="tk-item"
    :class="{ on: tool.name === selected }"
    @click="emit('select', tool.name)"
  >
    <span class="dot" :class="{ off: !tool.active }"></span>
    <span class="tk-item-name">{{ tool.name }}</span>
  </button>
</template>
