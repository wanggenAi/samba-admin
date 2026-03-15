import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "../auth/store";

import Dashboard from "../views/dashboard/DashboardView.vue";
import Users from "../views/users/UsersView.vue";
import UserCreate from "../views/users/UserCreateView.vue";
import UserEdit from "../views/users/UserEditView.vue";
import OuManager from "../views/ous/OuManagerView.vue";
import Login from "../views/auth/LoginPage.vue";
import SystemAdmin from "../views/system/SystemAdminView.vue";
import Forbidden from "../views/system/ForbiddenView.vue";

const routes = [
  { path: "/", redirect: "/dashboard" },
  { path: "/login", component: Login, meta: { public: true } },
  { path: "/forbidden", component: Forbidden, meta: { public: true } },
  { path: "/dashboard", component: Dashboard, meta: { permission: "dashboard.view" } },
  { path: "/config", redirect: "/dashboard" },
  { path: "/versions", redirect: "/dashboard" },
  { path: "/users", component: Users, meta: { permission: "users.view" } },
  { path: "/users/new", component: UserCreate, meta: { permission: "users.create" } },
  { path: "/users/edit/:username", component: UserEdit, meta: { permission: "users.edit" } },
  { path: "/ous", component: OuManager, meta: { permission: "ous.view" } },
  { path: "/system-admin", component: SystemAdmin, meta: { permission: "system.manage" } },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (to.meta.public) {
    if (to.path === "/login" && auth.isLoggedIn()) {
      try {
        if (!auth.user()) await auth.fetchMe();
      } catch {
        return true;
      }
      return "/dashboard";
    }
    return true;
  }

  if (!auth.isLoggedIn()) {
    return { path: "/login", query: { next: to.fullPath } };
  }

  if (!auth.user()) {
    try {
      await auth.fetchMe();
    } catch {
      return { path: "/login", query: { next: to.fullPath } };
    }
  }

  const permission = to.meta.permission;
  if (permission && !auth.hasPermission(permission)) {
    return "/forbidden";
  }

  return true;
});

export default router;
