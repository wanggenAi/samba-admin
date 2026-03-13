<template>
  <div class="create-page">
    <div class="page-head">
      <h2>New User</h2>
      <button class="btn" type="button" @click="closeWindow">Close</button>
    </div>

    <section class="panel panel-loading-host" :class="{ loading: dataLoading }">
      <div class="panel-head">
        <h3>Create / Overwrite</h3>
        <button class="btn primary" :disabled="submitting || dataLoading" @click="submit">
          {{ submitting ? "Submitting..." : "Submit" }}
        </button>
      </div>
      <details class="username-help">
        <summary>Username rule</summary>
        <div class="muted">
          Username is optional. If left blank, it is auto-generated from first/last name and student ID
          (`first.last`, `firstlast`, `last`, `first`, `student_id`, `user`) with numeric suffix if needed.
        </div>
      </details>

      <div class="grid">
        <label>
          Username (optional)
          <input v-model.trim="form.username" type="text" placeholder="u10001 or leave blank" />
          <span v-if="fieldErrors.username" class="field-error">{{ fieldErrors.username }}</span>
        </label>
        <label>
          Password
          <div class="password-row">
            <input
              v-model="form.password"
              :type="showPassword ? 'text' : 'password'"
              placeholder="Test@123456"
              autocomplete="new-password"
            />
            <button class="btn" type="button" @click="showPassword = !showPassword">
              {{ showPassword ? "Hide" : "Show" }}
            </button>
          </div>
          <span v-if="fieldErrors.password" class="field-error">{{ fieldErrors.password }}</span>
        </label>
        <label>
          First Name
          <input v-model.trim="form.first_name" type="text" placeholder="Ivan" @blur="onNameFieldBlur" />
          <span v-if="fieldErrors.first_name" class="field-error">{{ fieldErrors.first_name }}</span>
        </label>
        <label>
          Last Name
          <input v-model.trim="form.last_name" type="text" placeholder="Ivanov" @blur="onNameFieldBlur" />
          <span v-if="fieldErrors.last_name" class="field-error">{{ fieldErrors.last_name }}</span>
        </label>
        <label>
          Student ID
          <input v-model.trim="form.student_id" type="text" placeholder="2026001" />
          <span v-if="fieldErrors.student_id" class="field-error">{{ fieldErrors.student_id }}</span>
        </label>
        <label>
          Paid Flag (optional)
          <input v-model.trim="form.paid_flag" type="text" placeholder="$" maxlength="1" />
          <span v-if="fieldErrors.paid_flag" class="field-error">{{ fieldErrors.paid_flag }}</span>
        </label>
        <label class="full-row">
          Display Name (optional)
          <input
            v-model.trim="form.display_name"
            type="text"
            placeholder="Auto: First Name + Last Name"
            @input="onDisplayNameInput"
            @blur="onDisplayNameBlur"
          />
          <span class="muted">If left blank, it auto-fills from First Name + Last Name on blur.</span>
          <span v-if="fieldErrors.display_name" class="field-error">{{ fieldErrors.display_name }}</span>
        </label>
      </div>

      <div class="ou-picker">
        <label>OU Path (single select)</label>
        <div class="muted">Single-select only: each user has one physical OU location in LDAP.</div>
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
            @keydown.esc.prevent="closeOuDropdown"
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
        <span v-if="fieldErrors.ou_path" class="field-error">{{ fieldErrors.ou_path }}</span>
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
            @keydown.esc.prevent="closeGroupDropdown"
          />
        </div>

        <div v-if="groupDropdownOpen" class="dropdown">
          <div class="dropdown-actions">
            <button type="button" class="btn btn-xs" @click="selectAllVisibleGroups">Select visible</button>
            <button type="button" class="btn btn-xs" :disabled="!selectedGroups.length" @click="clearVisibleGroups">
              Clear visible
            </button>
          </div>
          <label
            v-for="(g, idx) in filteredGroups"
            :key="g.cn"
            class="dropdown-item checkbox-item"
          >
            <input
              type="checkbox"
              :checked="isGroupChecked(g.cn)"
              @change="onToggleGroupFromList(g.cn, idx, $event)"
            />
            <span>{{ g.cn }}</span>
          </label>
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
      <DataLoadingOverlay :show="dataLoading" text="Loading form data..." />
    </section>

    <div v-if="submitPhase !== 'idle'" class="submit-mask" role="status" aria-live="polite">
      <div class="submit-mask-card" :class="{ success: submitPhase === 'success' }">
        <h4>{{ submitPhase === "success" ? "Success" : "Submitting..." }}</h4>
        <p>
          {{
            submitPhase === "success"
              ? submitMessage || "User saved successfully."
              : "Creating or updating user, please wait..."
          }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import DataLoadingOverlay from "../../components/DataLoadingOverlay.vue";
import { useRouter } from "vue-router";
import { apiAddUser, apiListLdapGroups, apiListLdapOuTree } from "../../api/client";

const router = useRouter();
const groups = ref([]);
const ouTree = ref([]);
const loadingGroups = ref(false);
const loadingOuTree = ref(false);
const submitting = ref(false);
const error = ref("");
const fieldErrors = ref({});
const submitMessage = ref("");
const submitPhase = ref("idle");
const showPassword = ref(false);
const displayNameCustomized = ref(false);

const groupKeyword = ref("");
const selectedGroups = ref([]);
const groupDropdownOpen = ref(false);
const groupInputRef = ref(null);
const lastGroupToggleIndex = ref(-1);

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
  username: "",
  password: "",
  student_id: "",
  first_name: "",
  last_name: "",
  display_name: "",
  paid_flag: "",
});

const filteredGroups = computed(() => {
  const kw = groupKeyword.value.trim().toLowerCase();
  if (!kw) return groups.value.slice(0, 100);
  return groups.value.filter((g) => (g.cn || "").toLowerCase().includes(kw)).slice(0, 100);
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
const dataLoading = computed(() => loadingGroups.value || loadingOuTree.value);

function pickGroup(cn) {
  if (!cn || selectedGroups.value.includes(cn)) return;
  selectedGroups.value.push(cn);
  groupKeyword.value = "";
}

function addTypedGroup() {
  const typed = groupKeyword.value.trim();
  if (!typed) return;
  pickGroup(typed);
}

function removeGroup(cn) {
  selectedGroups.value = selectedGroups.value.filter((x) => x !== cn);
}

function isGroupChecked(cn) {
  return selectedGroups.value.includes(cn);
}

function setGroupChecked(cn, checked) {
  if (!cn) return;
  if (checked) {
    if (!selectedGroups.value.includes(cn)) {
      selectedGroups.value = [...selectedGroups.value, cn];
    }
    return;
  }
  selectedGroups.value = selectedGroups.value.filter((x) => x !== cn);
}

function onToggleGroupFromList(cn, index, event) {
  const checked = Boolean(event?.target?.checked);
  if (!event?.shiftKey || lastGroupToggleIndex.value < 0) {
    setGroupChecked(cn, checked);
    lastGroupToggleIndex.value = index;
    return;
  }

  const start = Math.min(lastGroupToggleIndex.value, index);
  const end = Math.max(lastGroupToggleIndex.value, index);
  const next = new Set(selectedGroups.value);
  const list = filteredGroups.value;
  for (let i = start; i <= end; i += 1) {
    const targetCn = String(list[i]?.cn || "").trim();
    if (!targetCn) continue;
    if (checked) next.add(targetCn);
    else next.delete(targetCn);
  }
  selectedGroups.value = Array.from(next);
  lastGroupToggleIndex.value = index;
}

function selectAllVisibleGroups() {
  const next = new Set(selectedGroups.value);
  for (const g of filteredGroups.value) {
    const cn = String(g?.cn || "").trim();
    if (cn) next.add(cn);
  }
  selectedGroups.value = Array.from(next);
}

function clearVisibleGroups() {
  if (!selectedGroups.value.length) return;
  const visible = new Set(filteredGroups.value.map((g) => String(g?.cn || "").trim()).filter(Boolean));
  selectedGroups.value = selectedGroups.value.filter((cn) => !visible.has(cn));
}

function focusGroupInput() {
  groupInputRef.value?.focus();
}

function closeGroupDropdown() {
  groupDropdownOpen.value = false;
  groupKeyword.value = "";
}

function buildAutoDisplayName() {
  return `${form.value.first_name || ""} ${form.value.last_name || ""}`.trim();
}

function onDisplayNameInput() {
  const current = String(form.value.display_name || "").trim();
  if (!current) {
    displayNameCustomized.value = false;
    return;
  }
  displayNameCustomized.value = current !== buildAutoDisplayName();
}

function onNameFieldBlur() {
  const current = String(form.value.display_name || "").trim();
  if (!current || !displayNameCustomized.value) {
    form.value.display_name = buildAutoDisplayName();
    displayNameCustomized.value = false;
  }
}

function onDisplayNameBlur() {
  const current = String(form.value.display_name || "").trim();
  if (!current) {
    form.value.display_name = buildAutoDisplayName();
    displayNameCustomized.value = false;
  }
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

function closeOuDropdown() {
  ouDropdownOpen.value = false;
  ouKeyword.value = "";
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
  if (window.opener && !window.opener.closed) {
    try {
      window.opener.postMessage({ type: "USER_EDITOR_CLOSED" }, window.location.origin);
    } catch {
      // ignore cross-window notification errors
    }
  }
  window.close();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function onClickOutside(event) {
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (!target.closest(".group-picker")) {
    closeGroupDropdown();
  }
  if (!target.closest(".ou-picker")) {
    closeOuDropdown();
  }
}

async function refreshGroups() {
  loadingGroups.value = true;
  error.value = "";
  try {
    groups.value = await apiListLdapGroups({ includeMembers: false, includeDescription: false });
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loadingGroups.value = false;
  }
}

async function refreshOuTree() {
  loadingOuTree.value = true;
  error.value = "";
  try {
    ouTree.value = await apiListLdapOuTree({ includeUsers: false });
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loadingOuTree.value = false;
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
      username: form.value.username || null,
      password: form.value.password,
      student_id: form.value.student_id,
      first_name: form.value.first_name,
      last_name: form.value.last_name,
      display_name: form.value.display_name || null,
      paid_flag: form.value.paid_flag || null,
      groups: selectedGroups.value,
      ou_path: parseOuPath(selectedOuPath.value),
    };

    const res = await apiAddUser(payload);
    const movedText = res.moved ? " moved" : "";
    submitMessage.value = `Success: ${res.username} (${res.created ? "created" : "updated"}${movedText}).`;
    submitPhase.value = "success";
    await sleep(1400);

    // If opened from Users list in a separate window, notify parent and close.
    if (window.opener && !window.opener.closed) {
      try {
        window.opener.postMessage({ type: "USER_CREATED_OR_UPDATED", username: res.username }, window.location.origin);
      } catch {
        // ignore cross-window notification errors
      }
      closeWindow();
      return;
    }

    // Fallback: if opened directly, go back to list page.
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

      if (Object.keys(nextFieldErrors).length) {
        fieldErrors.value = nextFieldErrors;
      } else {
        error.value = e?.message || String(e);
      }
    } else {
      error.value = e?.message || String(e);
    }
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  document.addEventListener("click", onClickOutside);
  await Promise.all([refreshGroups(), refreshOuTree()]);
});

onUnmounted(() => {
  document.removeEventListener("click", onClickOutside);
});
</script>

<style scoped>
.create-page {
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
.panel-loading-host {
  position: relative;
}
.panel-loading-host.loading {
  pointer-events: none;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.username-help {
  margin: -4px 0 10px;
  color: #64748b;
  font-size: 13px;
}
.username-help summary {
  cursor: pointer;
  user-select: none;
}
.username-help[open] {
  display: grid;
  gap: 6px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  column-gap: 10px;
  row-gap: 12px;
}
.full-row {
  grid-column: 1 / -1;
}
.password-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.password-row input {
  flex: 1;
}
.password-row .btn {
  min-width: 72px;
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
.dropdown-actions {
  display: flex;
  gap: 6px;
  position: sticky;
  top: 0;
  z-index: 1;
  background: #fff;
  padding-bottom: 4px;
}
.btn-xs {
  padding: 4px 8px;
  font-size: 12px;
  border-radius: 6px;
}
.dropdown-item {
  text-align: left;
  border: 1px solid transparent;
  border-radius: 6px;
  background: #fff;
  padding: 8px;
}
.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
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
  color: #777;
}
.submit-mask {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(15, 23, 42, 0.2);
  backdrop-filter: blur(1px);
  display: grid;
  place-items: center;
}
.submit-mask-card {
  width: min(92vw, 460px);
  padding: 16px 18px;
  border-radius: 12px;
  border: 1px solid #cbd5e1;
  background: #ffffff;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.16);
}
.submit-mask-card h4 {
  margin: 0 0 6px;
  font-size: 18px;
}
.submit-mask-card p {
  margin: 0;
  color: #475569;
}
.submit-mask-card.success {
  border-color: #86efac;
  background: #f0fdf4;
}
@media (max-width: 880px) {
  .grid {
    grid-template-columns: 1fr;
  }
  .combo-input {
    min-width: 160px;
  }
}
</style>
