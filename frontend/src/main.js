import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import { setAuthTokenGetter } from "./api/client";
import { useAuthStore } from "./auth/store";
import "./style.css";

const auth = useAuthStore();
setAuthTokenGetter(() => auth.token());

const BUILD_SYNC_ONCE_KEY = "samba_admin_build_sync_once";

async function syncWithLatestBuild() {
  const currentEntry = document
    .querySelector('script[type="module"][src*="/assets/index-"]')
    ?.getAttribute("src");
  if (!currentEntry) return;

  try {
    const res = await fetch("/index.html", { cache: "no-store" });
    const html = await res.text();
    const match = html.match(/src="(\/assets\/index-[^"]+\.js)"/);
    const latestEntry = match?.[1] || "";
    if (!latestEntry || latestEntry === currentEntry) {
      sessionStorage.removeItem(BUILD_SYNC_ONCE_KEY);
      return;
    }

    if (sessionStorage.getItem(BUILD_SYNC_ONCE_KEY) === "1") return;
    sessionStorage.setItem(BUILD_SYNC_ONCE_KEY, "1");
    const url = new URL(window.location.href);
    url.searchParams.set("__v", String(Date.now()));
    window.location.replace(url.toString());
  } catch {
    // Ignore build sync failures; regular navigation still works.
  }
}

syncWithLatestBuild();

createApp(App).use(router).mount("#app");
