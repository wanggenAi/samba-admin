import { reactive } from "vue";
import { apiLogin, apiMe } from "../api/client";

const TOKEN_KEY = "samba_admin_access_token";

const state = reactive({
  token: localStorage.getItem(TOKEN_KEY) || "",
  user: null,
  loadingMe: false,
});

function normalizeUser(user) {
  if (!user || typeof user !== "object") return null;
  const permissions = Array.isArray(user.permissions) ? user.permissions : [];
  const roles = Array.isArray(user.roles) ? user.roles : [];
  return {
    ...user,
    roles,
    permissions,
  };
}

function setToken(token) {
  state.token = token || "";
  if (state.token) localStorage.setItem(TOKEN_KEY, state.token);
  else localStorage.removeItem(TOKEN_KEY);
}

function setUser(user) {
  state.user = normalizeUser(user);
}

function clearAuth() {
  setToken("");
  setUser(null);
}

function hasPermission(permission) {
  const user = state.user;
  if (!user) return false;
  const perms = new Set(user.permissions || []);
  return perms.has("*") || perms.has(permission);
}

async function login(username, password) {
  const res = await apiLogin({ username, password });
  setToken(res?.access_token || "");
  setUser(res?.user || null);
  return state.user;
}

async function fetchMe() {
  if (!state.token) {
    setUser(null);
    return null;
  }
  if (state.loadingMe) return state.user;
  state.loadingMe = true;
  try {
    const me = await apiMe();
    setUser(me);
    return state.user;
  } catch (err) {
    if (err && (err.status === 401 || err.status === 403)) {
      clearAuth();
    }
    throw err;
  } finally {
    state.loadingMe = false;
  }
}

export function useAuthStore() {
  return {
    state,
    token: () => state.token,
    user: () => state.user,
    isLoggedIn: () => !!state.token,
    setToken,
    setUser,
    clearAuth,
    hasPermission,
    login,
    fetchMe,
  };
}

