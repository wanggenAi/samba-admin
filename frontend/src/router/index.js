import { createRouter, createWebHistory } from "vue-router";
import Dashboard from "../views/Dashboard.vue";
import Config from "../views/Config.vue";
import Versions from "../views/Versions.vue";

const routes = [
    { path: "/", redirect: "/dashboard" },
    { path: "/dashboard", component: Dashboard },
    { path: "/config", component: Config },
    { path: "/versions", component: Versions },
];

export default createRouter({
    history: createWebHistory(),
    routes,
});