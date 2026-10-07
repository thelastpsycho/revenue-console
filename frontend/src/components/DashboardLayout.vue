<template>
  <div class="min-h-screen bg-slate-100">
    <AppSidebar :open="sidebarOpen" @close="sidebarOpen = false" />

    <!-- Content column (offset by sidebar on desktop) -->
    <div class="flex min-h-screen flex-col lg:pl-64">
      <!-- Mobile top bar -->
      <header
        class="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-slate-200 bg-white px-4 lg:hidden"
      >
        <button
          type="button"
          class="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-colors hover:text-slate-900 cursor-pointer"
          @click="sidebarOpen = true"
        >
          <span class="sr-only">Open navigation</span>
          <Bars3Icon class="h-5 w-5" />
        </button>
        <span class="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white">
            <ChartBarSquareIcon class="h-4 w-4" />
          </span>
          Revenue Console
        </span>
      </header>

      <DedgeCodeBanner />

      <main class="flex flex-1 flex-col">
        <slot></slot>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Bars3Icon, ChartBarSquareIcon } from '@heroicons/vue/24/outline'
import AppSidebar from './AppSidebar.vue'
import DedgeCodeBanner from './DedgeCodeBanner.vue'

const sidebarOpen = ref(false)
const route = useRoute()

// Close the mobile drawer on navigation.
watch(() => route.path, () => {
  sidebarOpen.value = false
})
</script>
