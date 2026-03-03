<template>
  <div class="container">
    <h2>Samba Admin Console</h2>

    <section class="card">
      <div class="row">
        <button @click="loadStatus">Refresh Status</button>
        <span>Service: <b>{{ status.service }}</b></span>
        <span>Status: <b>{{ status.raw }}</b></span>
        <span :class="status.active ? 'ok' : 'bad'">
          ● {{ status.active ? 'Running' : 'Stopped' }}
        </span>
      </div>
    </section>

    <section class="card">
      <h3>Configuration</h3>

      <div class="row">
        <button @click="validate">Validate Config</button>
        <button @click="apply">Apply Config</button>
      </div>

      <textarea
        :value="output"
        rows="14"
        readonly
        placeholder="Output will appear here..."
      ></textarea>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from "vue";

const status = reactive({
  service: "smbd",
  active: false,
  raw: "unknown"
});

const output = ref("");

const payload = {
  shares: [
    {
      name: "testshare",
      path: "/data/testshare",
      browseable: true,
      read_only: false,
      guest_ok: true
    }
  ]
};

async function loadStatus() {
  const res = await fetch("/api/system/status");
  const data = await res.json();
  status.service = data.service;
  status.active = data.active;
  status.raw = data.raw;
}

async function validate() {
  const res = await fetch("/api/config/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  output.value = JSON.stringify(await res.json(), null, 2);
}

async function apply() {
  const res = await fetch("/api/config/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  output.value = JSON.stringify(await res.json(), null, 2);
}

onMounted(loadStatus);
</script>

<style>
.container {
  max-width: 900px;
  margin: 30px auto;
  font-family: Arial, sans-serif;
}

.card {
  border: 1px solid #ddd;
  padding: 16px;
  margin-bottom: 20px;
  border-radius: 8px;
}

.row {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

textarea {
  width: 100%;
  font-family: ui-monospace, Menlo, monospace;
}

button {
  padding: 6px 12px;
  cursor: pointer;
}

.ok {
  color: green;
}

.bad {
  color: red;
}
</style>