<template>
  <section class="forbidden">
    <h2>403 Forbidden</h2>
    <p>You do not have permission to access this page.</p>
    <RouterLink class="btn" to="/dashboard">Back to Dashboard</RouterLink>
  </section>
</template>

<script setup>
import { RouterLink } from "vue-router";
</script>

<style scoped>
.forbidden {
  max-width: 720px;
  margin: 40px auto;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 24px;
}
h2 {
  margin: 0 0 8px;
  color: #111827;
}
p {
  margin: 0 0 16px;
  color: #4b5563;
}
.btn {
  text-decoration: none;
  display: inline-block;
  border-radius: 8px;
  padding: 8px 12px;
  background: #1d4ed8;
  color: #fff;
}
</style>
