import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import { setAuthTokenGetter } from "./api/client";
import { useAuthStore } from "./auth/store";
import "./style.css";

const auth = useAuthStore();
setAuthTokenGetter(() => auth.token());

createApp(App).use(router).mount("#app");
