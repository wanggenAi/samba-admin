<template>
  <div class="wrap">
    <header class="top">
      <div class="brand">Samba Admin Console</div>

      <nav class="nav">
        <RouterLink to="/dashboard">Dashboard</RouterLink>
        <RouterLink to="/users">Users</RouterLink>
      </nav>
    </header>

    <main class="main">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { RouterLink, RouterView } from "vue-router";
</script>

<style scoped>
.wrap {
  max-width: 980px;
  margin: 0 auto;
  font-family: Arial, sans-serif;
}
.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 12px;
  border-bottom: 1px solid #eee;
}
.brand {
  font-size: 18px;
  font-weight: 700;
}
.nav {
  display: flex;
  gap: 10px;
}
.nav a {
  text-decoration: none;
  color: #333;
  padding: 6px 10px;
  border-radius: 8px;
}
.nav a.router-link-active {
  background: #efefef;
}
.main {
  padding: 12px;
}
</style>
