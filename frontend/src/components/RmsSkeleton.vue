<template>
  <dl v-if="variant === 'tiles'" class="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-hidden="true">
    <div v-for="i in count" :key="i" class="stat-tile animate-pulse">
      <div class="h-2.5 w-20 rounded bg-slate-200"></div>
      <div class="mt-2.5 h-5 w-16 rounded bg-slate-200"></div>
      <div class="mt-2 h-2.5 w-24 rounded bg-slate-100"></div>
    </div>
  </dl>
  <table v-else-if="variant === 'table'" class="data-table" aria-hidden="true">
    <tbody>
      <tr v-for="i in count" :key="i" class="animate-pulse">
        <td v-for="c in columns" :key="c">
          <div class="h-3 rounded bg-slate-200" :style="{ width: c === 1 ? '70%' : '85%' }"></div>
        </td>
      </tr>
    </tbody>
  </table>
  <div
    v-else-if="variant === 'chart'"
    class="h-full w-full animate-pulse rounded bg-slate-100"
    aria-hidden="true"
  ></div>
</template>
<script setup lang="ts">
withDefaults(
  defineProps<{
    variant: "tiles" | "table" | "chart";
    count?: number;
    columns?: number;
  }>(),
  { count: 5, columns: 5 },
);
</script>
