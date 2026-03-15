<template>
  <div class="login-page">
    <div class="bg-shape bg-shape-a"></div>
    <div class="bg-shape bg-shape-b"></div>

    <section class="login-card">
      <header class="login-head">
        <div class="uni-mark">БрГТУ</div>
        <h1>Samba Admin Console</h1>
        <p>Role-based secure access</p>
      </header>

      <p v-if="error" class="error">{{ error }}</p>

      <label class="field">
        <span>Username</span>
        <input v-model.trim="username" type="text" autocomplete="username" />
      </label>

      <label class="field">
        <span>Password</span>
        <input v-model="password" type="password" autocomplete="current-password" @keydown.enter="submit" />
      </label>

      <button class="btn-login" :disabled="submitting || !username || !password" @click="submit">
        {{ submitting ? "Signing in..." : "Sign in" }}
      </button>

    </section>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useRoute } from "vue-router";
import { useAuthStore } from "../../auth/store";

const route = useRoute();
const auth = useAuthStore();

const username = ref("");
const password = ref("");
const submitting = ref(false);
const error = ref("");

async function submit() {
  if (!username.value || !password.value || submitting.value) return;
  submitting.value = true;
  error.value = "";
  try {
    await auth.login(username.value, password.value);
    const nextRaw = typeof route.query.next === "string" ? route.query.next.trim() : "";
    const next = nextRaw && nextRaw !== "/login" ? nextRaw : "/dashboard";
    window.location.replace(next);
  } catch (err) {
    error.value = err?.message || "Login failed";
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  position: relative;
  overflow: hidden;
  background: linear-gradient(145deg, #edf3ff 0%, #ffffff 52%, #f5f8ff 100%);
  padding: 20px;
}
.bg-shape {
  position: absolute;
  pointer-events: none;
}
.bg-shape-a {
  width: 44vw;
  max-width: 520px;
  height: 44vw;
  max-height: 520px;
  border-radius: 50%;
  top: -16vw;
  left: -10vw;
  background: radial-gradient(circle at 30% 30%, #1f4ea9 0%, #143a84 60%, rgba(20, 58, 132, 0) 70%);
  opacity: 0.22;
}
.bg-shape-b {
  width: 38vw;
  max-width: 460px;
  height: 38vw;
  max-height: 460px;
  border-radius: 50%;
  right: -8vw;
  bottom: -14vw;
  background: radial-gradient(circle at 40% 40%, #bf1f3d 0%, #8f1330 58%, rgba(143, 19, 48, 0) 70%);
  opacity: 0.12;
}
.login-card {
  width: min(460px, 96vw);
  background: #fff;
  border: 1px solid #d8e3fb;
  border-radius: 16px;
  box-shadow: 0 18px 60px rgba(15, 43, 92, 0.15);
  padding: 28px 24px 22px;
  position: relative;
  z-index: 1;
}
.login-head {
  margin-bottom: 16px;
}
.uni-mark {
  display: inline-block;
  background: #143a84;
  color: #fff;
  font-size: 12px;
  letter-spacing: 0.07em;
  padding: 4px 8px;
  border-radius: 999px;
  margin-bottom: 10px;
}
.login-head h1 {
  margin: 0;
  color: #0f2d66;
  font-size: 24px;
}
.login-head p {
  margin: 6px 0 0;
  color: #4d607f;
}
.field {
  display: grid;
  gap: 7px;
  margin-top: 12px;
}
.field span {
  color: #1a2f56;
  font-weight: 600;
  font-size: 13px;
}
.field input {
  width: 100%;
  border: 1px solid #c6d6f4;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 14px;
  outline: none;
}
.field input:focus {
  border-color: #1f4ea9;
  box-shadow: 0 0 0 3px rgba(31, 78, 169, 0.18);
}
.btn-login {
  margin-top: 16px;
  width: 100%;
  border: 0;
  border-radius: 10px;
  padding: 11px 14px;
  background: linear-gradient(90deg, #143a84, #1f4ea9);
  color: #fff;
  font-weight: 700;
  cursor: pointer;
}
.btn-login:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.error {
  color: #991b1b;
  background: #fee2e2;
  border: 1px solid #fecaca;
  border-radius: 10px;
  padding: 9px 10px;
}
@media (max-width: 600px) {
  .login-card {
    padding: 22px 16px 16px;
  }
}
</style>
