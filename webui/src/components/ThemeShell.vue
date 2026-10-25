<script setup lang="ts">
import { useThemeVars } from 'naive-ui'
import { computed } from 'vue'

const themeVars = useThemeVars()

// Naive UI exposes its theme as component-scoped CSS variables, not on :root.
// Custom layout styles need their own variables, so mirror the values here.
const style = computed(() => ({
  '--tk-border': themeVars.value.borderColor,
  '--tk-panel': themeVars.value.cardColor,
  '--tk-text': themeVars.value.textColor1,
  '--tk-muted': themeVars.value.textColor3,
  '--tk-hover': themeVars.value.actionColor,
  '--tk-accent': themeVars.value.primaryColor,
  '--tk-success': themeVars.value.successColor,
  '--tk-error': themeVars.value.errorColor,
  '--tk-embedded': themeVars.value.bodyColor,
}))
</script>

<template>
  <div class="tk-shell" :style="style">
    <slot />
  </div>
</template>
