<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '../i18n'

const props = defineProps<{ total: number; applied: number; pending: number }>()
const { t } = useI18n('views.hotfix')

const text = computed(() =>
  t('summary', '{total} 个补丁 · {applied} 个已应用 · {pending} 个待应用')
    .replace('{total}', String(props.total))
    .replace('{applied}', String(props.applied))
    .replace('{pending}', String(props.pending)),
)
</script>

<template>
  <span class="tk-count">{{ text }}</span>
</template>
