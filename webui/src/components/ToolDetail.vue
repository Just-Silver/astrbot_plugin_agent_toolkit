<script setup lang="ts">
import { NTag } from 'naive-ui'
import type { ToolInfo } from '../bridge'
import { useI18n } from '../i18n'

defineProps<{ tool: ToolInfo | null }>()
const { t } = useI18n()
</script>

<template>
  <div class="tk-head">
    <span class="tk-name">{{ tool?.name || t('empty', '当前没有注册任何工具') }}</span>
    <NTag v-if="tool" size="small" :type="tool.active ? 'success' : 'default'" round>
      {{ tool.active ? t('enabled', '已启用') : t('disabled', '已禁用') }}
    </NTag>
  </div>
  <p v-if="tool?.description" class="tk-desc">{{ tool.description }}</p>
</template>
