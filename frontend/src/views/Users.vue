<template>
  <div class="users-page">
    <h2>Users</h2>

    <section class="panel">
      <div class="panel-head">
        <h3>Add User</h3>
        <button class="btn" :disabled="submitting || loadingUsers" @click="submit">
          {{ submitting ? "Submitting..." : "Create / Overwrite" }}
        </button>
      </div>

      <div class="grid">
        <label>
          Username
          <input v-model.trim="form.username" type="text" placeholder="u10001" />
          <span v-if="fieldErrors.username" class="field-error">{{ fieldErrors.username }}</span>
        </label>
        <label>
          Password
          <input v-model="form.password" type="password" placeholder="Test@123456" />
          <span v-if="fieldErrors.password" class="field-error">{{ fieldErrors.password }}</span>
        </label>
        <label>
          Student ID
          <input v-model.trim="form.student_id" type="text" placeholder="2026001" />
          <span v-if="fieldErrors.student_id" class="field-error">{{ fieldErrors.student_id }}</span>
        </label>
        <label>
          Russian Name
          <input v-model.trim="form.russian_name" type="text" placeholder="Иван Иванов" />
          <span v-if="fieldErrors.russian_name" class="field-error">{{ fieldErrors.russian_name }}</span>
        </label>
        <label>
          Pinyin Name
          <input v-model.trim="form.pinyin_name" type="text" placeholder="Zhang San" />
          <span v-if="fieldErrors.pinyin_name" class="field-error">{{ fieldErrors.pinyin_name }}</span>
        </label>
        <label>
          Paid Flag (optional)
          <input v-model.trim="form.paid_flag" type="text" placeholder="$" maxlength="1" />
          <span v-if="fieldErrors.paid_flag" class="field-error">{{ fieldErrors.paid_flag }}</span>
        </label>
      </div>

      <div class="ou-picker">
        <label>
          OU Path (optional)
          <input v-model.trim="form.ou_path_text" type="text" placeholder="Students/ms/101" />
        </label>
        <div class="ou-quick">
          <span class="muted">Quick pick:</span>
          <button
            v-for="path in ouPathOptions.slice(0, 16)"
            :key="path"
            type="button"
            class="btn mini"
            @click="applyOuPath(path)"
          >
            {{ path }}
          </button>
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
            class="group-input"
            type="text"
            placeholder="Type to search or input a group CN, then Enter"
            @focus="dropdownOpen = true"
            @keydown.enter.prevent="addTypedGroup"
            @keydown.esc="dropdownOpen = false"
          />
        </div>

        <div v-if="dropdownOpen" class="dropdown">
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

    <section class="panel">
      <div class="panel-head">
        <h3>User List</h3>
        <div class="panel-actions">
          <input
            v-model.trim="userKeyword"
            type="text"
            class="search-input"
            placeholder="Search username / display name / UPN / DN"
          />
          <button class="btn" :disabled="loadingUsers" @click="refreshUsers">
            {{ loadingUsers ? "Loading..." : "Refresh" }}
          </button>
        </div>
      </div>

      <div class="table-wrap">
        <table class="user-table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Display Name</th>
              <th>UPN</th>
              <th>DN</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in paginatedUsers" :key="u.dn">
              <td class="mono">{{ u.sAMAccountName || "-" }}</td>
              <td>{{ u.displayName || "-" }}</td>
              <td class="mono">{{ u.userPrincipalName || "-" }}</td>
              <td class="dn">{{ u.dn }}</td>
            </tr>
            <tr v-if="!filteredUsers.length" class="empty-row">
              <td colspan="4" class="muted">No users found.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pager" v-if="filteredUsers.length">
        <div class="pager-block pager-summary">
          <span class="muted">Total</span>
          <strong>{{ filteredUsers.length }}</strong>
          <span class="muted">users</span>
        </div>
        <div class="pager-block pager-size">
          <label>
            Page size
            <select v-model.number="pageSize">
              <option :value="10">10</option>
              <option :value="20">20</option>
              <option :value="50">50</option>
            </select>
          </label>
        </div>

        <div class="pager-block pager-nav">
          <button class="btn pager-btn" :disabled="currentPage <= 1" @click="goPrevPage">Prev</button>
          <span class="page-indicator">Page {{ currentPage }} / {{ totalPages }}</span>
          <button class="btn pager-btn" :disabled="currentPage >= totalPages" @click="goNextPage">Next</button>
        </div>
      </div>

      <p class="muted">Delete feature will be added next.</p>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h3>OU Tree</h3>
        <button class="btn" :disabled="loadingOuTree" @click="refreshOuTree">
          {{ loadingOuTree ? "Loading..." : "Refresh" }}
        </button>
      </div>

      <div v-if="!ouTreeLines.length" class="muted">No OU nodes found under current base DN.</div>
      <div v-else class="ou-tree-wrap">
        <div v-for="line in ouTreeLines" :key="line.key" class="ou-row" :style="{ paddingLeft: `${line.depth * 18}px` }">
          <span class="tree-tag" :class="line.type">{{ line.type === "ou" ? "OU" : "User" }}</span>
          <span class="mono">{{ line.text }}</span>
          <span class="dn muted">{{ line.dn }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { apiAddUser, apiListLdapGroups, apiListLdapOuTree, apiListLdapUsers } from "../api/client";

const users = ref([]);
const groups = ref([]);
const ouTree = ref([]);
const loadingUsers = ref(false);
const loadingGroups = ref(false);
const loadingOuTree = ref(false);
const submitting = ref(false);
const error = ref("");
const fieldErrors = ref({});
const submitMessage = ref("");
const groupKeyword = ref("");
const selectedGroups = ref([]);
const dropdownOpen = ref(false);
const groupInputRef = ref(null);
const userKeyword = ref("");
const currentPage = ref(1);
const pageSize = ref(10);

const form = ref({
  username: "",
  password: "",
  student_id: "",
  russian_name: "",
  pinyin_name: "",
  paid_flag: "",
  ou_path_text: "",
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
      out.push(currentPath.join("/"));
      walk(node.children || [], currentPath);
    }
  };
  walk(ouTree.value, []);
  return out;
});

const ouTreeLines = computed(() => {
  const out = [];
  const walk = (nodes, depth) => {
    for (const node of nodes || []) {
      out.push({
        key: `ou:${node.dn}`,
        depth,
        type: "ou",
        text: node.ou,
        dn: node.dn,
      });
      for (const u of node.users || []) {
        out.push({
          key: `user:${u.dn}`,
          depth: depth + 1,
          type: "user",
          text: u.sAMAccountName || u.displayName || u.dn,
          dn: u.dn,
        });
      }
      walk(node.children || [], depth + 1);
    }
  };
  walk(ouTree.value, 0);
  return out;
});

const filteredUsers = computed(() => {
  const kw = userKeyword.value.trim().toLowerCase();
  if (!kw) return users.value;

  return users.value.filter((u) => {
    const fields = [u.sAMAccountName, u.displayName, u.userPrincipalName, u.dn];
    return fields.some((value) => (value || "").toLowerCase().includes(kw));
  });
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredUsers.value.length / pageSize.value)));

const paginatedUsers = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredUsers.value.slice(start, start + pageSize.value);
});

function pickGroup(cn) {
  if (!cn || selectedGroups.value.includes(cn)) return;
  selectedGroups.value.push(cn);
  groupKeyword.value = "";
  dropdownOpen.value = false;
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

function onClickOutside(event) {
  if (!event.target.closest(".group-picker")) {
    dropdownOpen.value = false;
  }
}

async function refreshUsers() {
  loadingUsers.value = true;
  error.value = "";
  try {
    users.value = await apiListLdapUsers();
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loadingUsers.value = false;
  }
}

function goPrevPage() {
  if (currentPage.value > 1) {
    currentPage.value -= 1;
  }
}

function goNextPage() {
  if (currentPage.value < totalPages.value) {
    currentPage.value += 1;
  }
}

function parseOuPath(raw) {
  if (!raw) return [];
  return raw
    .split("/")
    .map((v) => v.trim())
    .filter(Boolean);
}

function applyOuPath(path) {
  form.value.ou_path_text = path || "";
}

async function refreshGroups() {
  loadingGroups.value = true;
  error.value = "";
  try {
    groups.value = await apiListLdapGroups();
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
    ouTree.value = await apiListLdapOuTree();
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loadingOuTree.value = false;
  }
}

async function submit() {
  submitting.value = true;
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
      ou_path: parseOuPath(form.value.ou_path_text),
    };

    const res = await apiAddUser(payload);
    const movedText = res.moved ? " moved" : "";
    submitMessage.value = `Success: ${res.username} (${res.created ? "created" : "updated"}${movedText}).`;
    await Promise.all([refreshUsers(), refreshOuTree()]);
  } catch (e) {
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
  await Promise.all([refreshUsers(), refreshGroups(), refreshOuTree()]);
});

onUnmounted(() => {
  document.removeEventListener("click", onClickOutside);
});

watch([userKeyword, pageSize], () => {
  currentPage.value = 1;
});

watch(totalPages, (next) => {
  if (currentPage.value > next) {
    currentPage.value = next;
  }
});
</script>

<style scoped>
.users-page { display: grid; gap: 16px; }
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
.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.search-input {
  width: 320px;
  max-width: 52vw;
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  gap: 10px;
}
label { display: grid; gap: 6px; font-size: 14px; }
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
.group-picker { margin-top: 12px; display: grid; gap: 8px; position: relative; }
.ou-picker {
  margin-top: 12px;
  display: grid;
  gap: 8px;
}
.ou-quick {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.btn.mini {
  padding: 4px 8px;
  font-size: 12px;
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
.group-input {
  border: none;
  outline: none;
  min-width: 280px;
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
.dropdown-item:hover { background: #f3f4f6; }
.dropdown-item.create { color: #1d4ed8; }
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
.table-wrap {
  overflow: auto;
  border: 1px solid #eceff3;
  border-radius: 12px;
  background: linear-gradient(180deg, #fbfdff 0%, #ffffff 100%);
}
.user-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}
.user-table th,
.user-table td {
  border-bottom: 1px solid #edf0f3;
  padding: 11px 14px;
  text-align: left;
  vertical-align: top;
}
.user-table th {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #64748b;
  background: #f8fafc;
  position: sticky;
  top: 0;
  z-index: 1;
}
.user-table tbody tr:hover {
  background: #f8fbff;
}
.user-table tbody tr:last-child td {
  border-bottom: none;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}
.dn {
  max-width: 420px;
  word-break: break-all;
  color: #334155;
}
.empty-row td {
  text-align: center;
  padding: 20px 12px;
}
.ou-tree-wrap {
  border: 1px solid #eceff3;
  border-radius: 12px;
  padding: 10px;
  background: #fbfdff;
  display: grid;
  gap: 6px;
}
.ou-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  flex-wrap: wrap;
}
.tree-tag {
  border-radius: 999px;
  font-size: 11px;
  line-height: 1;
  padding: 4px 7px;
  border: 1px solid #dbe3ef;
  color: #334155;
  background: #eff6ff;
}
.tree-tag.user {
  background: #f8fafc;
}
.pager {
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.pager-block {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pager-summary {
  min-width: 150px;
}
.pager-summary strong {
  font-size: 20px;
  line-height: 1;
  color: #0f172a;
}
.pager-size label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #334155;
}
.pager-nav {
  margin-left: auto;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 4px;
  gap: 6px;
  background: #f8fafc;
}
.pager-btn {
  min-width: 72px;
  background: #fff;
}
.page-indicator {
  font-size: 14px;
  color: #475569;
  padding: 0 6px;
}
select {
  border: 1px solid #d2d8e0;
  border-radius: 8px;
  padding: 6px 8px;
  margin-left: 0;
  background: #fff;
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
.muted { color: #777; }
@media (max-width: 800px) {
  .grid { grid-template-columns: 1fr; }
  .group-input { min-width: 180px; }
  .panel-head {
    flex-direction: column;
    align-items: stretch;
  }
  .panel-actions {
    width: 100%;
  }
  .search-input {
    width: 100%;
    max-width: none;
  }
  .user-table th,
  .user-table td {
    padding: 10px;
  }
  .pager {
    align-items: stretch;
  }
  .pager-summary {
    min-width: 0;
  }
  .pager-size {
    width: 100%;
  }
  .pager-size label {
    width: 100%;
    justify-content: space-between;
  }
  .pager-nav {
    width: 100%;
    justify-content: space-between;
    margin-left: 0;
  }
  .page-indicator {
    margin: 0 auto;
  }
}
</style>
