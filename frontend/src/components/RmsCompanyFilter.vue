<template>
  <div ref="menuRef" class="relative">
    <span class="field-label">Company</span>
    <button
      type="button"
      class="neu-input flex items-center gap-2 whitespace-nowrap"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ buttonLabel }}
    </button>
    <div
      v-if="open"
      class="neu-card absolute left-0 top-full z-30 mt-1 w-72 space-y-2 p-3 shadow-lg"
    >
      <input
        v-model="search"
        type="search"
        placeholder="Search companies…"
        class="neu-input w-full"
      />
      <div class="max-h-56 space-y-1 overflow-y-auto">
        <label
          v-for="c in filtered"
          :key="c.id"
          class="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-slate-50"
        >
          <input
            type="checkbox"
            class="accent-slate-900"
            :checked="selected.has(c.id)"
            @change="toggle(c.id)"
          />
          {{ c.name }}
        </label>
        <p v-if="!filtered.length" class="px-2 py-1.5 text-xs text-slate-500">
          No companies match "{{ search }}".
        </p>
      </div>
      <div class="flex items-center justify-between border-t border-slate-200 pt-2">
        <button
          type="button"
          class="btn-flat px-2 py-1 text-xs"
          :disabled="!modelValue.length"
          @click="$emit('update:modelValue', [])"
        >
          Clear
        </button>
        <button type="button" class="btn-primary px-3 py-1 text-xs" @click="open = false">
          Done
        </button>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
export interface CompanyOption {
  id: number;
  name: string;
}
const props = defineProps<{
  companies: CompanyOption[];
  modelValue: number[];
}>();
const emit = defineEmits<{ "update:modelValue": [value: number[]] }>();
const open = ref(false);
const search = ref("");
const menuRef = ref<HTMLElement | null>(null);
const selected = computed(() => new Set(props.modelValue));
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase();
  return q ? props.companies.filter((c) => c.name.toLowerCase().includes(q)) : props.companies;
});
const buttonLabel = computed(() => {
  const n = props.modelValue.length;
  if (!n) return "All companies";
  if (n === 1)
    return props.companies.find((c) => c.id === props.modelValue[0])?.name || "1 company";
  return `${n} companies`;
});
function toggle(id: number) {
  emit(
    "update:modelValue",
    selected.value.has(id)
      ? props.modelValue.filter((v) => v !== id)
      : [...props.modelValue, id],
  );
}
function onClickOutside(e: MouseEvent) {
  if (open.value && menuRef.value && !menuRef.value.contains(e.target as Node)) open.value = false;
}
onMounted(() => document.addEventListener("mousedown", onClickOutside));
onBeforeUnmount(() => document.removeEventListener("mousedown", onClickOutside));
</script>
