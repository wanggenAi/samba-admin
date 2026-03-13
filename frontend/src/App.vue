<template>
  <div class="layout">
    <header v-if="!isLoginPage" class="top">
      <div class="top-inner">
        <div class="brand">
          <div class="brand-line-a">БрГТУ</div>
          <div class="brand-line-b">Samba Admin Console</div>
        </div>

        <nav class="nav">
          <RouterLink v-if="has('dashboard.view')" to="/dashboard">Dashboard</RouterLink>
          <RouterLink v-if="has('users.view')" to="/users">Users</RouterLink>
          <RouterLink v-if="has('ous.view')" to="/ous">OUs</RouterLink>
          <RouterLink v-if="has('system.manage')" to="/system-admin">System</RouterLink>
        </nav>

        <div class="account">
          <span class="who">{{ userName }}</span>
          <button class="logout" @click="logout">Logout</button>
        </div>
      </div>
    </header>

    <main class="main" :class="{ 'main-login': isLoginPage }">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { useAuthStore } from "./auth/store";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const isLoginPage = computed(() => route.path === "/login");
const userName = computed(() => auth.user()?.username || "guest");

function has(permission) {
  return auth.hasPermission(permission);
}

function logout() {
  auth.clearAuth();
  router.replace("/login");
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
}
.top {
  position: sticky;
  top: 0;
  z-index: 30;
  border-bottom: 3px solid #bf1f3d;
  background: linear-gradient(90deg, #0f2f6b, #1f4ea9);
  color: #fff;
}
.top-inner {
  max-width: 1540px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 260px 1fr auto;
  align-items: center;
  gap: 16px;
  padding: 12px 14px;
}
.brand-line-a {
  font-size: 11px;
  letter-spacing: 0.09em;
  opacity: 0.9;
}
.brand-line-b {
  font-size: 18px;
  font-weight: 700;
}
.nav {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.nav a {
  text-decoration: none;
  color: #eef4ff;
  padding: 7px 10px;
  border-radius: 8px;
}
.nav a.router-link-active {
  background: rgba(255, 255, 255, 0.18);
}
.account {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.who {
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 13px;
}
.logout {
  border: 0;
  border-radius: 8px;
  padding: 7px 10px;
  background: #ffffff;
  color: #143a84;
  cursor: pointer;
  font-weight: 600;
}
.main {
  max-width: 1540px;
  margin: 0 auto;
  padding: 14px;
}
.main-login {
  max-width: none;
  margin: 0;
  padding: 0;
}
@media (max-width: 980px) {
  .top-inner {
    grid-template-columns: 1fr;
    gap: 10px;
  }
  .account {
    justify-self: start;
  }
}
</style>
