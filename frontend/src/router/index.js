import { createRouter, createWebHistory } from "vue-router";

const Dashboard = () => import("../views/Dashboard.vue");
const Config = () => import("../views/Config.vue");
const Versions = () => import("../views/Versions.vue");
const Users = () => import("../views/Users.vue");
const UserCreate = () => import("../views/UserCreate.vue");
const UserEdit = () => import("../views/UserEdit.vue");
const OuManager = () => import("../views/OuManager.vue");

const routes = [
    { path: "/", redirect: "/dashboard" },
    { path: "/dashboard", component: Dashboard },
    { path: "/config", component: Config },
    { path: "/versions", component: Versions },
    { path: "/users", component: Users },
    { path: "/users/new", component: UserCreate },
    { path: "/users/edit/:username", component: UserEdit },
    { path: "/ous", component: OuManager },
];

export default createRouter({
    history: createWebHistory(),
    routes,
});
