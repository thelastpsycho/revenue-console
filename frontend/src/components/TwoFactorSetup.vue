<template>
  <div class="space-y-2 text-xs">
    <h3 v-if="heading" class="text-sm font-semibold">{{ heading }}</h3>

    <template v-if="!setupSecret">
      <p class="text-slate-500">{{ description }}</p>
      <p v-if="error" class="font-semibold text-rose-700">{{ error }}</p>
      <button type="button" class="btn-flat py-1.5" :disabled="busy" @click="start">
        {{ busy ? "Starting…" : "Enable" }}
      </button>
    </template>

    <template v-else>
      <p class="text-slate-600">
        Scan this with an authenticator app (Google Authenticator, Authy, etc.), or enter the key manually.
      </p>
      <img :src="qrDataUri" alt="Authenticator QR code" class="h-40 w-40" />
      <p class="break-all text-slate-500">Key: <span class="font-mono">{{ setupSecret }}</span></p>
      <form class="space-y-2" @submit.prevent="confirm">
        <label class="block">
          <span class="mb-1 block font-semibold text-slate-600">Enter the 6-digit code</span>
          <input v-model="confirmCode" type="text" inputmode="numeric" maxlength="6" required class="neu-input w-full" />
        </label>
        <p v-if="error" class="font-semibold text-rose-700">{{ error }}</p>
        <div class="flex items-center gap-2">
          <button type="submit" class="btn-primary py-1.5" :disabled="busy">
            {{ busy ? "Confirming…" : "Confirm" }}
          </button>
          <button type="button" class="font-semibold text-slate-500 hover:text-slate-900" @click="cancel">
            Cancel
          </button>
        </div>
      </form>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import axios from "../plugins/axios";
import { useAuthStore } from "../stores/auth";

withDefaults(defineProps<{
  heading?: string
  description?: string
}>(), {
  heading: "Two-factor authentication",
  description: "Not enabled. Protects your account with a code from an authenticator app.",
});

const emit = defineEmits<{ (e: "enabled"): void }>();

const auth = useAuthStore();
const busy = ref(false);
const error = ref("");
const setupSecret = ref("");
const qrDataUri = ref("");
const confirmCode = ref("");

async function start() {
  busy.value = true;
  error.value = "";
  try {
    const { data } = await axios.post("/api/auth/2fa/setup");
    setupSecret.value = data.secret;
    qrDataUri.value = data.qrDataUri;
  } catch (err: any) {
    error.value = err?.response?.data?.message || "Could not start setup.";
  } finally {
    busy.value = false;
  }
}

function cancel() {
  setupSecret.value = "";
  qrDataUri.value = "";
  confirmCode.value = "";
  error.value = "";
}

async function confirm() {
  busy.value = true;
  error.value = "";
  try {
    await axios.post("/api/auth/2fa/confirm", { code: confirmCode.value });
    cancel();
    await auth.refresh();
    emit("enabled");
  } catch (err: any) {
    error.value = err?.response?.data?.message || "Invalid code.";
  } finally {
    busy.value = false;
  }
}
</script>
