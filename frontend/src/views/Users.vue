<template>
  <div class="users-page">
    <header class="page-head">
      <div>
        <h2>Users</h2>
        <p class="sub">Browse OU structure, filter users, and bulk-delete selected accounts.</p>
      </div>
      <button class="btn primary" type="button" @click="openAddWindow">New User</button>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="actionMessage" class="ok">{{ actionMessage }}</p>

    <div class="workspace">
      <section class="panel tree-panel">
        <div class="panel-head">
          <h3>OU Tree</h3>
          <div class="panel-actions">
            <input
              v-model.trim="ouKeyword"
              type="text"
              class="search-input"
              placeholder="Search OU / user / DN"
            />
            <button class="btn" :disabled="loadingOuTree" @click="onRefreshTree">
              {{ loadingOuTree ? "Loading..." : "Refresh" }}
            </button>
          </div>
        </div>

        <div v-if="!ouTreeLines.length" class="muted">No OU nodes found under current base DN.</div>
        <div v-else class="ou-tree-wrap">
          <div
            v-for="line in ouTreeLines"
            :key="line.key"
            class="ou-row clickable"
            :class="{ active: line.type === 'ou' && selectedOuDn && selectedOuDn.toLowerCase() === line.dn.toLowerCase() }"
            :style="{ paddingLeft: `${line.depth * 18}px` }"
            :title="line.dn"
            @click="onTreeLineClick(line)"
          >
            <span class="tree-tag" :class="line.type">{{ line.type === "ou" ? "OU" : "User" }}</span>
            <span class="main-text">{{ line.text }}</span>
          </div>
        </div>
      </section>

      <section class="panel list-panel">
        <div class="panel-head list-head">
          <div class="head-left">
            <h3>User List</h3>
            <div v-if="selectedOuDn" class="active-filter">
              <span class="muted">OU filter:</span>
              <code>{{ selectedOuPath || selectedOuDn }}</code>
            </div>
          </div>
          <div class="panel-actions list-actions">
            <button
              class="btn danger"
              :disabled="!selectedUsernames.length || deletingBatch"
              @click="onBatchDelete"
            >
              {{ deletingBatch ? "Deleting..." : `Delete Selected (${selectedUsernames.length})` }}
            </button>
            <input
              v-model.trim="userKeyword"
              type="text"
              class="search-input"
              placeholder="Search username / display name / UPN / DN / OU path"
            />
            <button class="btn" :disabled="loadingUsers" @click="onRefreshUsers">
              {{ loadingUsers ? "Loading..." : "Refresh" }}
            </button>
          </div>
        </div>

        <div class="table-wrap">
          <table class="user-table">
            <thead>
              <tr>
                <th class="check-col">
                  <input
                    type="checkbox"
                    :checked="allCurrentPageSelected"
                    @change="toggleSelectCurrentPage($event.target.checked)"
                  />
                </th>
                <th>Username</th>
                <th>Display Name</th>
                <th>Pinyin</th>
                <th>Student ID</th>
                <th>Paid</th>
                <th>UPN</th>
                <th>DN</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in paginatedUsers" :key="u.dn">
                <td class="check-col">
                  <input
                    type="checkbox"
                    :disabled="isProtectedUsername(resolveUsername(u))"
                    :title="isProtectedUsername(resolveUsername(u)) ? 'Protected account' : ''"
                    :checked="selectedUsernames.includes(resolveUsername(u))"
                    @change="toggleSelectUser(resolveUsername(u), $event.target.checked)"
                  />
                </td>
                <td class="mono">{{ u.sAMAccountName || "-" }}</td>
                <td>{{ u.displayName || "-" }}</td>
                <td>{{ u.givenName || "-" }}</td>
                <td class="mono">{{ u.employeeID || "-" }}</td>
                <td class="mono">{{ u.employeeType || "-" }}</td>
                <td class="mono">{{ u.userPrincipalName || "-" }}</td>
                <td class="dn mono" :title="u.dn">{{ u.dn }}</td>
              </tr>
              <tr v-if="!filteredUsers.length" class="empty-row">
                <td colspan="8" class="muted">No users found.</td>
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
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { apiDeleteUser, apiListLdapOuTree, apiListLdapUsers } from "../api/client";

const users = ref([]);
const ouTree = ref([]);
const loadingUsers = ref(false);
const loadingOuTree = ref(false);
const error = ref("");
const actionMessage = ref("");
const userKeyword = ref("");
const ouKeyword = ref("");
const selectedOuDn = ref("");
const selectedOuPath = ref("");
const currentPage = ref(1);
const pageSize = ref(10);
const deletingBatch = ref(false);
const selectedUsernames = ref([]);
const protectedUsernames = new Set(["krbtgt"]);

const ouTreeLines = computed(() => {
  const kw = ouKeyword.value.trim().toLowerCase();

  const collect = (nodes, depth, path) => {
    const lines = [];
    let matchedAny = false;

    for (const node of nodes || []) {
      const currentPath = [...path, node.ou];
      const pathText = currentPath.join("/");

      const nodeLine = {
        key: `ou:${node.dn}`,
        depth,
        type: "ou",
        text: node.ou,
        dn: node.dn,
        path: pathText,
      };

      const usersInNode = (node.users || []).map((u) => ({
        key: `user:${u.dn}`,
        depth: depth + 1,
        type: "user",
        text: u.sAMAccountName || u.displayName || u.dn,
        dn: u.dn,
        path: pathText,
      }));

      const child = collect(node.children || [], depth + 1, currentPath);
      const nodeHit = !kw || [nodeLine.text, nodeLine.dn, nodeLine.path].some((v) => (v || "").toLowerCase().includes(kw));
      const userHits = !kw
        ? usersInNode
        : usersInNode.filter((u) => [u.text, u.dn, u.path].some((v) => (v || "").toLowerCase().includes(kw)));
      const matched = nodeHit || userHits.length > 0 || child.matched;

      if (matched) {
        lines.push(nodeLine, ...userHits, ...child.lines);
      }
      matchedAny = matchedAny || matched;
    }

    return { lines, matched: matchedAny };
  };

  return collect(ouTree.value, 0, []).lines;
});

const filteredUsers = computed(() => {
  let items = users.value;
  if (selectedOuDn.value) {
    const target = normalizeDn(selectedOuDn.value);
    items = items.filter((u) => {
      const parentDn = parentDnOfUser(u.dn || "");
      return parentDn && normalizeDn(parentDn) === target;
    });
  }

  const kw = userKeyword.value.trim().toLowerCase();
  if (!kw) return items;

  return items.filter((u) => {
    const ouPath = extractOuPathFromDn(u.dn || "");
    const fields = [u.sAMAccountName, u.displayName, u.givenName, u.employeeID, u.employeeType, u.userPrincipalName, u.dn, ouPath];
    return fields.some((value) => (value || "").toLowerCase().includes(kw));
  });
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredUsers.value.length / pageSize.value)));

const paginatedUsers = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredUsers.value.slice(start, start + pageSize.value);
});

const currentPageUsernames = computed(() =>
  paginatedUsers.value
    .map((u) => resolveUsername(u))
    .filter((u) => u && !isProtectedUsername(u))
);

const allCurrentPageSelected = computed(() => {
  if (!currentPageUsernames.value.length) return false;
  return currentPageUsernames.value.every((u) => selectedUsernames.value.includes(u));
});

function extractOuPathFromDn(dn) {
  if (!dn) return "";
  const ous = [];
  for (const part of dn.split(",")) {
    const p = part.trim();
    if (p.toUpperCase().startsWith("OU=")) {
      ous.push(p.slice(3));
    }
  }
  return ous.reverse().join("/");
}

function normalizeDn(dn) {
  return String(dn || "")
    .split(",")
    .map((p) => p.trim().toLowerCase())
    .filter(Boolean)
    .join(",");
}

function parentDnOfUser(dn) {
  const raw = String(dn || "");
  const idx = raw.indexOf(",");
  if (idx < 0) return "";
  return raw.slice(idx + 1);
}

function extractCnFromDn(dn) {
  if (!dn) return "";
  const first = String(dn).split(",", 1)[0].trim();
  if (!first.toUpperCase().startsWith("CN=")) return "";
  return first.slice(3);
}

function resolveUsername(user) {
  return user?.sAMAccountName || extractCnFromDn(user?.dn || "");
}

function isProtectedUsername(username) {
  if (!username) return false;
  return protectedUsernames.has(String(username).toLowerCase());
}

function openAddWindow() {
  window.open("/users/new", "_blank", "noopener,noreferrer");
}

function clearOuFilter() {
  selectedOuDn.value = "";
  selectedOuPath.value = "";
}

function onRefreshUsers() {
  userKeyword.value = "";
  clearOuFilter();
  currentPage.value = 1;
  selectedUsernames.value = [];
  actionMessage.value = "";
  refreshUsers();
}

function onRefreshTree() {
  ouKeyword.value = "";
  clearOuFilter();
  actionMessage.value = "";
  refreshOuTree();
}

function onTreeLineClick(line) {
  if (!line) return;
  if (line.type === "ou") {
    if (selectedOuDn.value.toLowerCase() === (line.dn || "").toLowerCase()) {
      clearOuFilter();
      return;
    }
    selectedOuDn.value = line.dn;
    selectedOuPath.value = line.path || "";
    return;
  }

  const text = line.text || "";
  if (text) userKeyword.value = text;
  if (line.path) selectedOuPath.value = line.path;
}

function toggleSelectUser(username, checked) {
  if (!username || isProtectedUsername(username)) return;
  if (checked) {
    if (!selectedUsernames.value.includes(username)) {
      selectedUsernames.value = [...selectedUsernames.value, username];
    }
    return;
  }
  selectedUsernames.value = selectedUsernames.value.filter((u) => u !== username);
}

function toggleSelectCurrentPage(checked) {
  const pageUsers = currentPageUsernames.value;
  if (checked) {
    const merged = new Set([...selectedUsernames.value, ...pageUsers]);
    selectedUsernames.value = Array.from(merged);
    return;
  }
  const pageSet = new Set(pageUsers);
  selectedUsernames.value = selectedUsernames.value.filter((u) => !pageSet.has(u));
}

async function onBatchDelete() {
  const targets = [...selectedUsernames.value];
  if (!targets.length) return;
  const ok = window.confirm(`Delete ${targets.length} selected users? This cannot be undone.`);
  if (!ok) return;

  deletingBatch.value = true;
  error.value = "";
  actionMessage.value = "";
  const failed = [];

  for (const username of targets) {
    try {
      await apiDeleteUser(username);
    } catch (e) {
      failed.push({ username, message: e?.message || String(e) });
    }
  }

  selectedUsernames.value = [];
  await Promise.all([refreshUsers(), refreshOuTree()]);
  deletingBatch.value = false;

  if (!failed.length) {
    actionMessage.value = `Deleted ${targets.length} users`;
    return;
  }

  const okCount = targets.length - failed.length;
  const details = failed.map((x) => `${x.username}: ${x.message}`).join("; ");
  error.value = `Batch delete finished: success ${okCount}, failed ${failed.length}. ${details}`;
}

async function refreshUsers() {
  loadingUsers.value = true;
  error.value = "";
  try {
    users.value = await apiListLdapUsers();
    selectedUsernames.value = selectedUsernames.value.filter((name) =>
      users.value.some((u) => resolveUsername(u) === name)
    );
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loadingUsers.value = false;
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

function goPrevPage() {
  if (currentPage.value > 1) currentPage.value -= 1;
}

function goNextPage() {
  if (currentPage.value < totalPages.value) currentPage.value += 1;
}

async function onWindowMessage(event) {
  if (event.origin !== window.location.origin) return;
  if (!event.data || event.data.type !== "USER_CREATED_OR_UPDATED") return;
  actionMessage.value = `Saved user: ${event.data.username || "-"}`;
  await Promise.all([refreshUsers(), refreshOuTree()]);
}

onMounted(async () => {
  window.addEventListener("message", onWindowMessage);
  await Promise.all([refreshUsers(), refreshOuTree()]);
});

onUnmounted(() => {
  window.removeEventListener("message", onWindowMessage);
});

watch([userKeyword, selectedOuDn, pageSize], () => {
  currentPage.value = 1;
});

watch(totalPages, (next) => {
  if (currentPage.value > next) currentPage.value = next;
});
</script>

<style scoped>
.users-page {
  display: grid;
  gap: 16px;
}
.page-head {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  padding: 4px 2px;
}
.page-head h2 {
  margin: 0;
  line-height: 1.1;
}
.sub {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
}
.workspace {
  display: grid;
  gap: 18px;
  grid-template-columns: minmax(300px, 0.8fr) minmax(0, 2.2fr);
  align-items: stretch;
}
.panel {
  border: 1px solid #dde5ef;
  border-radius: 14px;
  padding: 14px;
  background: #ffffff;
  min-width: 0;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.tree-panel,
.list-panel {
  height: 68vh;
  min-height: 520px;
  display: flex;
  flex-direction: column;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.tree-panel .panel-head {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}
.tree-panel .panel-actions {
  justify-content: stretch;
}
.tree-panel .panel-actions > * {
  width: 100%;
}
.panel-head h3 {
  margin: 0;
  font-size: 20px;
  letter-spacing: -0.01em;
}
.tree-panel .panel-head h3 {
  font-size: 17px;
  letter-spacing: 0;
}
.list-head {
  align-items: start;
}
.head-left {
  display: grid;
  gap: 6px;
}
.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.list-actions {
  justify-content: flex-end;
}
.btn {
  height: 36px;
  padding: 0 14px;
  border: 1px solid #d3dde8;
  border-radius: 10px;
  background: #f8fafc;
  color: #0f172a;
  font-weight: 600;
}
.btn:hover {
  background: #eef2f7;
}
.btn:disabled {
  opacity: 0.6;
}
.btn.primary {
  background: #0f172a;
  border-color: #0f172a;
  color: #fff;
}
.btn.primary:hover {
  background: #111f38;
}
.btn.danger {
  background: #fff1f2;
  border-color: #fecdd3;
  color: #9f1239;
}
.search-input {
  width: 320px;
  max-width: 33vw;
  height: 36px;
  border: 1px solid #cfd8e3;
  border-radius: 10px;
  padding: 0 12px;
  background: #fff;
}
.active-filter {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  background: #f1f5f9;
  width: fit-content;
}
.table-wrap {
  flex: 1;
  overflow: auto;
  border: 1px solid #e6edf4;
  border-radius: 12px;
  background: #fff;
  max-height: none;
}
.user-table {
  width: 100%;
  min-width: 1200px;
  border-collapse: separate;
  border-spacing: 0;
}
.user-table th,
.user-table td {
  border-bottom: 1px solid #edf2f7;
  padding: 11px 12px;
  text-align: left;
  vertical-align: top;
}
.user-table th {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #64748b;
  background: #f8fbff;
  position: sticky;
  top: 0;
  z-index: 1;
}
.check-col {
  width: 44px;
  text-align: center !important;
}
.user-table tbody tr:hover {
  background: #f8fbff;
}
.user-table tbody tr:last-child td {
  border-bottom: none;
}
.empty-row td {
  text-align: center;
  padding: 20px 12px;
}
.ou-tree-wrap {
  flex: 1;
  border: 1px solid #e6edf4;
  border-radius: 12px;
  padding: 10px;
  background: #fbfdff;
  display: grid;
  gap: 6px;
  max-height: none;
  overflow: auto;
}
.ou-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 20px;
}
.ou-row.clickable {
  cursor: pointer;
  border-radius: 8px;
  padding: 3px 6px;
}
.ou-row.clickable:hover {
  background: #f1f5f9;
}
.ou-row.active {
  background: #e6f0ff;
}
.tree-tag {
  border-radius: 999px;
  font-size: 9px;
  line-height: 1;
  padding: 2px 6px;
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
.pager-nav {
  margin-left: auto;
  border: 1px solid #e2e8f0;
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
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}
.main-text {
  color: #0f172a;
  font-size: 13px;
  line-height: 1.1;
  font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif;
  font-weight: 600;
}
.dn {
  max-width: 520px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #475569;
}
.error {
  color: #b00020;
  background: #fde7ea;
  border: 1px solid #f5c2c7;
  padding: 10px;
  border-radius: 10px;
  white-space: pre-wrap;
}
.ok {
  color: #14532d;
  background: #dcfce7;
  border: 1px solid #86efac;
  padding: 10px;
  border-radius: 10px;
}
.muted {
  color: #77818f;
}

@media (max-width: 1200px) {
  .workspace {
    grid-template-columns: 1fr;
  }
  .search-input {
    width: 100%;
    max-width: none;
  }
  .panel-head {
    flex-direction: column;
    align-items: stretch;
  }
  .list-actions,
  .panel-actions {
    width: 100%;
    justify-content: stretch;
  }
  .list-actions > * {
    flex: 1;
    min-width: 0;
  }
  .table-wrap,
  .ou-tree-wrap {
    max-height: none;
  }
  .tree-panel,
  .list-panel {
    height: auto;
    min-height: 0;
  }
}
</style>
