<template>
  <div
    :class="[
      'flex flex-col gap-4 border-b border-slate-200 sm:flex-row sm:items-end sm:justify-between',
      compact ? 'pb-3' : 'pb-6',
    ]"
  >
    <div class="min-w-0">
      <h1
        :class="[
          'font-semibold tracking-tight text-slate-900',
          compact ? 'text-lg' : 'text-xl sm:text-2xl',
        ]"
      >
        {{ title }}
      </h1>
      <p
        v-if="subtitle"
        :class="[
          'max-w-2xl leading-relaxed text-slate-500',
          compact ? 'mt-1 text-xs' : 'mt-2 text-sm',
        ]"
      >
        {{ subtitle }}
      </p>
    </div>
    <div v-if="$slots.actions" class="flex flex-shrink-0 items-center gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
  compact?: boolean
}>()
</script>
