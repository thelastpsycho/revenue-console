<script setup lang="ts">
import DashboardLayout from './components/DashboardLayout.vue'
import AuthGate from './components/AuthGate.vue'
import AppDialog from './components/AppDialog.vue'
</script>

<template>
  <AuthGate>
    <DashboardLayout>
      <router-view />
    </DashboardLayout>
  </AuthGate>
  <AppDialog />
</template>

<style>
@tailwind base;
@tailwind components;
@tailwind utilities;
</style>
