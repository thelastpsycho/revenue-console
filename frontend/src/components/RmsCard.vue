<template>
  <section class="neu-card overflow-hidden">
    <div
      class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3"
    >
      <div class="min-w-0">
        <h2 class="text-sm font-semibold text-slate-900">{{ title }}</h2>
        <p v-if="description" class="mt-0.5 text-[11px] text-slate-500">
          {{ description }}
        </p>
      </div>
      <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2">
        <slot name="actions" />
      </div>
    </div>
    <div :class="[padded && 'p-4', scroll && 'max-h-[60vh] overflow-auto']">
      <slot />
    </div>
    <p
      v-if="$slots.empty"
      class="border-t border-slate-100 px-4 py-3 text-xs text-slate-500"
    >
      <slot name="empty" />
    </p>
  </section>
</template>
<script setup lang="ts">
// One card shell for every RMS report: title, one-line description, actions.
defineProps<{
  title: string;
  description?: string;
  padded?: boolean;
  scroll?: boolean;
}>();
</script>
