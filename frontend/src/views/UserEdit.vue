<template>
  <div class="edit-page">
    <div class="page-head">
      <h2>Edit User</h2>
      <button class="btn" type="button" @click="closeWindow">Close</button>
    </div>

    <section class="panel">
      <div class="panel-head">
        <h3>Update Existing User</h3>
        <button class="btn primary" :disabled="submitting || loadingInitial" @click="submit">
          {{ submitting ? "Saving..." : "Save" }}
        </button>
      </div>

      <p v-if="loadingInitial" class="muted">Loading user data...</p>

      <div class="grid">
        <label>
          Username
          <input v-model.trim="form.username" type="text" readonly />
        </label>
        <label>
          Password
          <div class="password-row">
            <input
              v-model="form.password"
              :type="showPassword ? 'text' : 'password'"
              placeholder="Leave blank to keep current password"
              autocomplete="new-password"
            />
            <button class="btn" type="button" @click="showPassword = !showPassword">
              {{ showPassword ? "Hide" : "Show" }}
            </button>
          </div>
          <span class="muted">Current password cannot be read from LDAP/AD. You can only set a new one.</span>
          <span v-if="fieldErrors.password" class="field-error">{{ fieldErrors.password }}</span>
        </label>
        <label>
          Student ID
          <input v-model.trim="form.student_id" type="text" />
          <span v-if="fieldErrors.student_id" class="field-error">{{ fieldErrors.student_id }}</span>
        </label>
        <label>
          Russian Name
          <input v-model.trim="form.russian_name" type="text" />
          <span v-if="fieldErrors.russian_name" class="field-error">{{ fieldErrors.russian_name }}</span>
        </label>
        <label>
          Pinyin Name
          <input v-model.trim="form.pinyin_name" type="text" />
          <span v-if="fieldErrors.pinyin_name" class="field-error">{{ fieldErrors.pinyin_name }}</span>
        </label>
        <label>
          Paid Flag (optional)
          <input v-model.trim="form.paid_flag" type="text" placeholder="$" maxlength="1" />
          <span v-if="fieldErrors.paid_flag" class="field-error">{{ fieldErrors.paid_flag }}</span>
        </label>
      </div>

      <div class="ou-picker">
        <label>OU Path (single select)</label>
        <div class="combo" @click="focusOuInput">
          <span v-if="selectedOuPath" class="chip">
            {{ selectedOuPath }}
            <button class="chip-x" type="button" @click.stop="clearOuPath">×</button>
          </span>
          <input
            ref="ouInputRef"
            v-model.trim="ouKeyword"
            class="combo-input"
            type="text"
            placeholder='Type OU path (e.g. Students > ms > 63/24 or ms-63/24), Enter to set'
            @focus="ouDropdownOpen = true"
            @keydown.enter.prevent="applyTypedOuPath"
            @keydown.esc="ouDropdownOpen = false"
          />
        </div>
        <div v-if="ouDropdownOpen" class="dropdown">
          <button
            v-for="path in filteredOuPaths"
            :key="path"
            type="button"
            class="dropdown-item"
            @click="pickOuPath(path)"
          >
            {{ path }}
          </button>
          <button
            v-if="ouKeyword && !hasExactOuPath"
            type="button"
            class="dropdown-item create"
            @click="applyTypedOuPath"
          >
            Use "{{ ouKeyword }}"
          </button>
          <div v-if="!filteredOuPaths.length && !(ouKeyword && !hasExactOuPath)" class="muted">
            No OU path matched.
          </div>
        </div>
      </div>

      <div class="group-picker">
        <label>Groups (multi-select, CN)</label>

        <div class="combo" @click="focusGroupInput">
          <span v-for="cn in selectedGroups" :key="cn" class="chip">
            {{ cn }}
            <button class="chip-x" type="button" @click.stop="removeGroup(cn)">×</button>
          </span>

          <input
            ref="groupInputRef"
            v-model.trim="groupKeyword"
            class="combo-input"
            type="text"
            placeholder="Type to search or input a group CN, then Enter"
            @focus="groupDropdownOpen = true"
            @keydown.enter.prevent="addTypedGroup"
            @keydown.esc="groupDropdownOpen = false"
          />
        </div>

        <div v-if="groupDropdownOpen" class="dropdown">
          <button
            v-for="g in filteredGroups"
            :key="g.cn"
            type="button"
            class="dropdown-item"
            @click="pickGroup(g.cn)"
          >
            {{ g.cn }}
          </button>
          <button
            v-if="groupKeyword && !hasExactGroup"
            type="button"
            class="dropdown-item create"
            @click="addTypedGroup"
          >
            Use "{{ groupKeyword }}"
          </button>
          <div v-if="!filteredGroups.length && !(groupKeyword && !hasExactGroup)" class="muted">
            No groups matched.
          </div>
        </div>

        <span v-if="fieldErrors.groups" class="field-error">{{ fieldErrors.groups }}</span>
      </div>

      <p v-if="submitMessage" class="ok">{{ submitMessage }}</p>
      <p v-if="error" class="error">{{ error }}</p>
    </section>

    <div v-if="submitPhase !== 'idle'" class="submit-mask" role="status" aria-live="polite">
      <div class="submit-mask-card" :class="{ success: submitPhase === 'success' }">
        <h4>{{ submitPhase === "success" ? "Saved" : "Saving..." }}</h4>
        <p>
          {{
            submitPhase === "success"
              ? submitMessage || "User updated successfully."
              : "Updating user, please wait..."
          }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { apiAddUser, apiListLdapGroups, apiListLdapOuTree, apiListLdapUsers } from "../api/client";

const route = useRoute();
const router = useRouter();
const username = String(route.params.username || "").trim();

const users = ref([]);
const groups = ref([]);
const ouTree = ref([]);
const loadingInitial = ref(false);
const loadingGroups = ref(false);
const loadingOuTree = ref(false);
const submitting = ref(false);
const error = ref("");
const fieldErrors = ref({});
const submitMessage = ref("");
const submitPhase = ref("idle");
const showPassword = ref(false);

const groupKeyword = ref("");
const selectedGroups = ref([]);
const groupDropdownOpen = ref(false);
const groupInputRef = ref(null);

const ouKeyword = ref("");
const selectedOuPath = ref("");
const ouDropdownOpen = ref(false);
const ouInputRef = ref(null);
const OU_PATH_SEPARATOR = ">";
const GROUP_CODE_MAP = {
  "МС": "ms",
  "ПЭ": "pe",
  "Э": "e",
  "КС": "ks",
  "ИИ": "ii",
};

const form = ref({
  username,
  password: "",
  student_id: "",
  russian_name: "",
  pinyin_name: "",
  paid_flag: "",
});

const filteredGroups = computed(() => {
  const kw = groupKeyword.value.toLowerCase();
  const available = groups.value.filter((g) => !selectedGroups.value.includes(g.cn));
  if (!kw) return available.slice(0, 20);
  return available.filter((g) => (g.cn || "").toLowerCase().includes(kw)).slice(0, 20);
});

const hasExactGroup = computed(() => {
  const kw = groupKeyword.value.trim().toLowerCase();
  if (!kw) return false;
  return groups.value.some((g) => (g.cn || "").toLowerCase() === kw);
});

const ouPathOptions = computed(() => {
  const out = [];
  const walk = (nodes, path) => {
    for (const node of nodes || []) {
      const currentPath = [...path, node.ou];
      out.push(currentPath.join(` ${OU_PATH_SEPARATOR} `));
      walk(node.children || [], currentPath);
    }
  };
  walk(ouTree.value, []);
  return out;
});

const filteredOuPaths = computed(() => {
  const kw = ouKeyword.value.trim().toLowerCase();
  const options = ouPathOptions.value.filter((p) => p !== selectedOuPath.value);
  if (!kw) return options.slice(0, 24);
  return options.filter((p) => p.toLowerCase().includes(kw)).slice(0, 24);
});

const hasExactOuPath = computed(() => {
  const kw = ouKeyword.value.trim().toLowerCase();
  if (!kw) return false;
  return ouPathOptions.value.some((p) => p.toLowerCase() === kw);
});

function normalizeDn(dn) {
  return String(dn || "")
    .split(",")
    .map((p) => p.trim().toLowerCase())
    .filter(Boolean)
    .join(",");
}

function extractOuPathFromDn(dn) {
  if (!dn) return "";
  const ous = [];
  for (const part of String(dn).split(",")) {
    const p = part.trim();
    if (p.toUpperCase().startsWith("OU=")) ous.push(p.slice(3));
  }
  return ous.reverse().join(` ${OU_PATH_SEPARATOR} `);
}

function pickGroup(cn) {
  if (!cn || selectedGroups.value.includes(cn)) return;
  selectedGroups.value = [...selectedGroups.value, cn];
  groupKeyword.value = "";
  groupDropdownOpen.value = false;
}

function addTypedGroup() {
  const typed = groupKeyword.value.trim();
  if (!typed) return;
  pickGroup(typed);
}

function removeGroup(cn) {
  selectedGroups.value = selectedGroups.value.filter((x) => x !== cn);
}

function focusGroupInput() {
  groupInputRef.value?.focus();
}

function pickOuPath(path) {
  if (!path) return;
  selectedOuPath.value = path;
  ouKeyword.value = "";
  ouDropdownOpen.value = false;
}

function applyTypedOuPath() {
  const typed = ouKeyword.value.trim();
  if (!typed) return;
  pickOuPath(typed);
}

function clearOuPath() {
  selectedOuPath.value = "";
}

function focusOuInput() {
  ouInputRef.value?.focus();
}

function parseOuPath(raw) {
  if (!raw) return [];
  const value = String(raw).trim();
  if (!value) return [];

  if (value.includes(OU_PATH_SEPARATOR)) {
    return value
      .split(/\s*>\s*/)
      .map((v) => v.trim())
      .filter(Boolean);
  }

  // Script-style shorthand: groupCode-groupNumber -> Students ; code ; number
  const m = value.match(/^([^-]+)-(.+)$/);
  if (m) {
    const rawCode = m[1].trim();
    const rawNumber = m[2].trim();
    const mappedCode = GROUP_CODE_MAP[rawCode.toUpperCase()] || rawCode.toLowerCase();
    if (mappedCode && rawNumber) {
      return ["Students", mappedCode, rawNumber];
    }
  }

  return [value];
}

function closeWindow() {
  window.close();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function onClickOutside(event) {
  const target = event.target;
  if (!target.closest(".group-picker")) groupDropdownOpen.value = false;
  if (!target.closest(".ou-picker")) ouDropdownOpen.value = false;
}

function prefillFromUser(user) {
  form.value.student_id = user?.employeeID || "";
  form.value.russian_name = user?.displayName || "";
  form.value.pinyin_name = user?.givenName || "";
  form.value.paid_flag = user?.employeeType || "";
  selectedOuPath.value = extractOuPathFromDn(user?.dn || "");

  const userDn = normalizeDn(user?.dn || "");
  const nextGroups = [];
  for (const g of groups.value) {
    const members = Array.isArray(g?.members) ? g.members : [];
    const hit = members.some((m) => normalizeDn(m) === userDn);
    if (hit && g?.cn) nextGroups.push(g.cn);
  }
  selectedGroups.value = nextGroups;
}

async function refreshUsers() {
  users.value = await apiListLdapUsers();
}

async function refreshGroups() {
  loadingGroups.value = true;
  try {
    groups.value = await apiListLdapGroups();
  } finally {
    loadingGroups.value = false;
  }
}

async function refreshOuTree() {
  loadingOuTree.value = true;
  try {
    ouTree.value = await apiListLdapOuTree();
  } finally {
    loadingOuTree.value = false;
  }
}

async function loadInitial() {
  if (!username) {
    error.value = "missing username in route";
    return;
  }

  loadingInitial.value = true;
  error.value = "";
  try {
    await Promise.all([refreshUsers(), refreshGroups(), refreshOuTree()]);
    const user = users.value.find((u) => String(u?.sAMAccountName || "").toLowerCase() === username.toLowerCase());
    if (!user) {
      error.value = `user not found: ${username}`;
      return;
    }
    prefillFromUser(user);
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loadingInitial.value = false;
  }
}

async function submit() {
  submitting.value = true;
  submitPhase.value = "submitting";
  error.value = "";
  fieldErrors.value = {};
  submitMessage.value = "";

  try {
    const payload = {
      username: form.value.username,
      password: form.value.password,
      student_id: form.value.student_id,
      russian_name: form.value.russian_name,
      pinyin_name: form.value.pinyin_name,
      paid_flag: form.value.paid_flag || null,
      groups: selectedGroups.value,
      ou_path: parseOuPath(selectedOuPath.value),
    };

    const res = await apiAddUser(payload);
    submitMessage.value = `Saved: ${res.username}`;
    submitPhase.value = "success";
    await sleep(1400);

    if (window.opener && !window.opener.closed) {
      try {
        window.opener.postMessage({ type: "USER_CREATED_OR_UPDATED", username: res.username }, window.location.origin);
      } catch {
        // ignore
      }
      window.close();
      return;
    }

    await router.push("/users");
  } catch (e) {
    submitPhase.value = "idle";
    const detail = e?.detail;
    if (Array.isArray(detail)) {
      const nextFieldErrors = {};
      for (const item of detail) {
        const path = Array.isArray(item?.loc) ? item.loc : [];
        const field = path[0] === "body" ? path[path.length - 1] : null;
        if (!field || nextFieldErrors[field]) continue;
        nextFieldErrors[field] = item?.msg || "Invalid value";
      }
      if (Object.keys(nextFieldErrors).length) fieldErrors.value = nextFieldErrors;
      else error.value = e?.message || String(e);
    } else {
      error.value = e?.message || String(e);
    }
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  document.addEventListener("click", onClickOutside);
  await loadInitial();
});

onUnmounted(() => {
  document.removeEventListener("click", onClickOutside);
});
</script>

<style scoped>
.edit-page {
  display: grid;
  gap: 16px;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.panel {
  border: 1px solid #e8e8e8;
  border-radius: 12px;
  padding: 14px;
  background: #fff;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  gap: 10px;
}
.password-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.password-row input {
  flex: 1;
}
label {
  display: grid;
  gap: 6px;
  font-size: 14px;
}
input {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 8px 10px;
}
input[readonly] {
  background: #f8fafc;
  color: #475569;
}
.btn {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: #f7f7f7;
}
.btn.primary {
  background: #0f172a;
  border-color: #0f172a;
  color: #fff;
}
.group-picker,
.ou-picker {
  margin-top: 12px;
  display: grid;
  gap: 8px;
  position: relative;
}
.combo {
  min-height: 42px;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 4px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.combo-input {
  border: none;
  outline: none;
  min-width: 260px;
  flex: 1;
}
.dropdown {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  max-height: 220px;
  overflow: auto;
  padding: 6px;
  display: grid;
  gap: 4px;
}
.dropdown-item {
  text-align: left;
  border: 1px solid transparent;
  border-radius: 6px;
  background: #fff;
  padding: 8px;
}
.dropdown-item:hover {
  background: #f3f4f6;
}
.dropdown-item.create {
  color: #1d4ed8;
}
.chip {
  background: #eef4ff;
  color: #224;
  border: 1px solid #cfe0ff;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.chip-x {
  border: none;
  background: transparent;
  color: #334155;
  padding: 0;
  width: 16px;
  height: 16px;
  line-height: 16px;
}
.error {
  color: #b00020;
  background: #fde7ea;
  border: 1px solid #f5c2c7;
  padding: 8px;
  border-radius: 8px;
  white-space: pre-wrap;
}
.field-error {
  color: #b00020;
  font-size: 12px;
  line-height: 1.3;
}
.ok {
  color: #14532d;
  background: #dcfce7;
  border: 1px solid #86efac;
  padding: 8px;
  border-radius: 8px;
}
.muted {
  color: #64748b;
}
.submit-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.2);
  display: grid;
  place-items: center;
  z-index: 1000;
}
.submit-mask-card {
  width: min(420px, calc(100vw - 40px));
  border-radius: 14px;
  border: 1px solid #dbeafe;
  background: #fff;
  box-shadow: 0 16px 50px rgba(15, 23, 42, 0.2);
  padding: 18px 20px;
}
.submit-mask-card h4 {
  margin: 0;
  font-size: 18px;
}
.submit-mask-card p {
  margin: 8px 0 0;
  color: #334155;
}
.submit-mask-card.success {
  border-color: #86efac;
}
</style>
