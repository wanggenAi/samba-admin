<template>
  <div class="page">
    <h2>Dashboard</h2>

    <div class="card">
      <div class="row">
        <button class="btn" :disabled="loading" @click="refresh">
          {{ loading ? "Loading..." : "Refresh Status" }}
        </button>

        <div class="meta" v-if="status">
          <span>Service: <b>{{ status.service }}</b></span>
          <span>Status: <b>{{ status.raw }}</b></span>
          <span class="dot" :class="{ ok: status.active, bad: !status.active }"></span>
          <span :class="{ okText: status.active, badText: !status.active }">
            {{ status.active ? "Running" : "Stopped" }}
          </span>
        </div>

        <div class="meta" v-else>
          <span class="muted">No status yet</span>
        </div>
      </div>

      <div v-if="error" class="error">
        {{ error }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { apiGetStatus } from "../api/client";

const status = ref(null);
const loading = ref(false);
const error = ref("");

async function refresh() {
  error.value = "";
  loading.value = true;
  try {
    status.value = await apiGetStatus();
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);
</script>

<style scoped>
.page { padding: 12px; }
.card {
  border: 1px solid #eee;
  border-radius: 12px;
  padding: 14px;
  max-width: 760px;
}
.row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.btn {
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid #ddd;
  background: #f7f7f7;
  cursor: pointer;
}
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.meta { display: flex; gap: 12px; align-items: center; }
.muted { color: #888; }
.dot {
  width: 8px; height: 8px; border-radius: 99px;
  background: #bbb;
}
.dot.ok { background: #2ecc71; }
.dot.bad { background: #e74c3c; }
.okText { color: #2ecc71; font-weight: 600; }
.badText { color: #e74c3c; font-weight: 600; }
.error {
  margin-top: 10px;
  color: #b00020;
  background: #fde7ea;
  border: 1px solid #f5c2c7;
  padding: 10px;
  border-radius: 10px;
  white-space: pre-wrap;
}
</style>