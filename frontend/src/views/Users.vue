<template>
  <div class="users-page">
    <header class="page-head">
      <div>
        <h2>Users</h2>
        <p class="sub">Browse OU structure, filter users, and bulk-delete selected accounts.</p>
      </div>
      <div class="page-head-actions">
        <input
          ref="importInputRef"
          class="file-input-hidden"
          type="file"
          accept=".txt,text/plain"
          multiple
          @change="onImportFiles"
        />
        <button class="btn" type="button" :disabled="importing" @click="triggerImport">
          {{ importing ? "Importing..." : "Import TXT" }}
        </button>
        <button class="btn" type="button" :disabled="exporting" @click="onExportUsers">
          {{ exporting ? "Exporting..." : "Export CSV" }}
        </button>
        <button class="btn primary" type="button" @click="openAddWindow">New User</button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="actionMessage" class="ok">{{ actionMessage }}</p>
    <section v-if="importReport" class="panel import-report">
      <div class="import-report-head">
        <h3>Import Report</h3>
        <button class="btn" type="button" @click="importReport = null">Close</button>
      </div>
      <p class="muted">
        Files: {{ importReport.total_files }} |
        Rows: {{ importReport.total_lines }} |
        Created: {{ importReport.created }} |
        Skipped: {{ importReport.skipped }} |
        Failed: {{ importReport.failed }}
      </p>
      <div class="import-table-wrap">
        <table class="import-table">
          <thead>
            <tr>
              <th>File</th>
              <th>Line</th>
              <th>Status</th>
              <th>Username</th>
              <th>Password</th>
              <th>Name</th>
              <th>OU Path</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in importReport.results" :key="`${item.file_name}:${item.line_no}:${idx}`">
              <td>{{ item.file_name }}</td>
              <td class="mono">{{ item.line_no || "-" }}</td>
              <td>
                <span class="import-status" :class="item.status">{{ item.status }}</span>
              </td>
              <td class="mono">{{ item.username || "-" }}</td>
              <td class="mono">{{ item.password || "-" }}</td>
              <td>{{ [item.first_name, item.last_name].filter(Boolean).join(" ") || "-" }}</td>
              <td>{{ item.ou_path?.length ? item.ou_path.join(" > ") : "-" }}</td>
              <td>{{ item.message }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div class="workspace">
      <section class="panel tree-panel">
        <div class="panel-head tree-head">
          <div class="tree-head-top">
            <h3>OU Tree</h3>
            <div class="tree-tools">
              <button class="btn tree-tool-btn" :disabled="loadingOuTree" title="Refresh tree" @click="onRefreshTree">
                {{ loadingOuTree ? "Loading" : "Refresh" }}
              </button>
              <button
                class="btn tree-tool-btn"
                type="button"
                :disabled="loadingOuTree || !ouTree.length"
                title="Expand all OU nodes"
                @click="onExpandAllOu"
              >
                +All
              </button>
              <button
                class="btn tree-tool-btn"
                type="button"
                :disabled="loadingOuTree || !ouTree.length"
                title="Collapse all OU nodes"
                @click="onCollapseAllOu"
              >
                -All
              </button>
            </div>
          </div>
          <div class="tree-search-row">
            <input
              v-model.trim="ouKeyword"
              type="text"
              class="search-input tree-search-input"
              placeholder="Search OU / user / DN"
            />
          </div>
        </div>

        <div v-if="!ouTreeLines.length" class="muted">No OU nodes found under current base DN.</div>
        <div v-else class="ou-tree-wrap">
          <div
            v-for="line in ouTreeLines"
            :key="line.key"
            class="ou-row"
            :class="{
              clickable: line.type === 'ou',
              active: line.type === 'ou' && selectedOuDn && selectedOuDn.toLowerCase() === line.dn.toLowerCase(),
            }"
            :style="{ paddingLeft: `${line.depth * 18}px` }"
            :title="line.dn"
            @click="onTreeLineClick(line)"
          >
            <button
              v-if="line.type === 'ou' && line.hasChildren"
              type="button"
              class="tree-toggle"
              :aria-label="line.expanded ? 'Collapse OU' : 'Expand OU'"
              @click.stop="onToggleOuExpand(line)"
            >
              {{ line.expanded ? "▾" : "▸" }}
            </button>
            <span v-else class="tree-toggle-placeholder" aria-hidden="true"></span>
            <span class="tree-tag" :class="line.type">{{ line.type === "ou" ? "OU" : "User" }}</span>
            <span class="main-text">{{ line.text }}</span>
          </div>
        </div>
      </section>

      <section class="panel list-panel">
        <div class="panel-head list-head">
          <div class="head-left">
            <h3>User List</h3>
            <div class="active-filters">
              <div v-if="selectedOuDn" class="active-filter">
                <span class="muted">OU filter:</span>
                <code>{{ selectedOuPath || selectedOuDn }}</code>
              </div>
              <div v-if="selectedGroups.length" class="active-filter">
                <span class="muted">Group filter:</span>
                <code>{{ selectedGroups.join(", ") }}</code>
              </div>
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
            <div class="group-filter-inline">
              <button
                class="btn"
                type="button"
                :disabled="loadingGroups"
                @click="groupDropdownOpen = !groupDropdownOpen"
              >
                {{ loadingGroups ? "Loading groups..." : `Groups (${selectedGroups.length})` }}
              </button>
              <div v-if="groupDropdownOpen" class="group-dropdown-panel">
                <input
                  v-model.trim="groupKeyword"
                  type="text"
                  class="group-search-input"
                  placeholder="Search groups"
                />
                <div class="group-checkbox-list">
                  <label v-for="g in filteredGroups" :key="g.cn" class="group-option">
                    <input
                      type="checkbox"
                      :checked="selectedGroups.includes(g.cn)"
                      @change="toggleGroup(g.cn, $event.target.checked)"
                    />
                    <span>{{ g.cn }}</span>
                  </label>
                  <div v-if="!filteredGroups.length" class="muted">No groups matched.</div>
                </div>
                <div class="group-panel-actions">
                  <button class="btn" type="button" :disabled="!selectedGroups.length" @click="clearGroupFilters">
                    Clear
                  </button>
                  <button class="btn" type="button" @click="groupDropdownOpen = false">Done</button>
                </div>
              </div>
            </div>
            <input
              v-model.trim="userKeyword"
              type="text"
              class="search-input"
              placeholder="Search username / first name / last name / display name / UPN / DN / OU path"
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
                <th class="username-col">Username</th>
                <th>Display Name</th>
                <th>First Name</th>
                <th>Last Name</th>
                <th>Student ID</th>
                <th>Paid</th>
                <th>UPN</th>
                <th>Updated At</th>
                <th>Groups</th>
                <th>DN</th>
                <th>Actions</th>
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
                <td class="mono username-col" :title="u.sAMAccountName || '-'">{{ u.sAMAccountName || "-" }}</td>
                <td>{{ u.displayName || "-" }}</td>
                <td>{{ u.givenName || "-" }}</td>
                <td>{{ u.sn || "-" }}</td>
                <td class="mono">{{ u.employeeID || "-" }}</td>
                <td class="mono">{{ u.employeeType || "-" }}</td>
                <td class="mono">{{ u.userPrincipalName || "-" }}</td>
                <td class="mono">{{ formatLdapTime(userUpdatedAt(u)) }}</td>
                <td>
                  <div class="group-cell">
                    <span
                      v-for="cn in groupsByUser(u)"
                      :key="`${u.dn}:${cn}`"
                      class="group-chip"
                    >
                      {{ cn }}
                    </span>
                    <span v-if="!groupsByUser(u).length" class="muted">-</span>
                  </div>
                </td>
                <td class="dn mono" :title="u.dn">{{ u.dn }}</td>
                <td>
                  <button
                    class="btn"
                    type="button"
                    @click.stop="openEditWindow(u)"
                  >
                    Edit
                  </button>
                </td>
              </tr>
              <tr v-if="!filteredUsers.length" class="empty-row">
                <td colspan="12" class="muted">No users found.</td>
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
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import {
  apiDeleteUser,
  apiExportUsers,
  apiImportUsers,
  apiListLdapGroups,
  apiListLdapOuTree,
  apiListLdapUsers,
} from "../api/client";

const users = shallowRef([]);
const groups = shallowRef([]);
const ouTree = shallowRef([]);
const loadingUsers = ref(false);
const loadingGroups = ref(false);
const loadingOuTree = ref(false);
const importing = ref(false);
const exporting = ref(false);
const error = ref("");
const actionMessage = ref("");
const importReport = shallowRef(null);
const userKeyword = ref("");
const ouKeyword = ref("");
const groupKeyword = ref("");
const selectedGroups = ref([]);
const groupDropdownOpen = ref(false);
const selectedOuDn = ref("");
const selectedOuPath = ref("");
const currentPage = ref(1);
const pageSize = ref(10);
const deletingBatch = ref(false);
const selectedUsernames = ref([]);
const expandedOuDns = ref(new Set());
const protectedUsernames = new Set(["krbtgt"]);
const importInputRef = ref(null);
const EMPTY_STR_LIST = Object.freeze([]);

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
        hasChildren: (node.children || []).length > 0 || (node.users || []).length > 0,
        expanded: isOuExpanded(node.dn),
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
        lines.push(nodeLine);
        const showChildren = kw ? true : nodeLine.expanded;
        if (showChildren) {
          lines.push(...userHits, ...child.lines);
        }
      }
      matchedAny = matchedAny || matched;
    }

    return { lines, matched: matchedAny };
  };

  return collect(ouTree.value, 0, []).lines;
});

const userGroupListMap = computed(() => {
  const out = new Map();
  for (const g of groups.value) {
    const cn = String(g?.cn || "").trim();
    if (!cn) continue;
    for (const memberDn of g?.members || []) {
      const key = normalizeDn(memberDn);
      if (!key) continue;
      if (!out.has(key)) out.set(key, []);
      const values = out.get(key);
      if (!values.includes(cn)) values.push(cn);
    }
  }
  for (const values of out.values()) {
    values.sort((a, b) => a.localeCompare(b));
  }
  return out;
});

const filteredGroups = computed(() => {
  const kw = groupKeyword.value.toLowerCase();
  if (!kw) return groups.value.slice(0, 100);
  return groups.value.filter((g) => (g.cn || "").toLowerCase().includes(kw)).slice(0, 100);
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

  if (selectedGroups.value.length) {
    const targets = new Set(selectedGroups.value.map((g) => g.toLowerCase()));
    items = items.filter((u) => {
      const values = groupsByUser(u);
      if (!values.length) return false;
      return values.some((g) => targets.has(g.toLowerCase()));
    });
  }

  const kw = userKeyword.value.trim().toLowerCase();
  if (kw) {
    items = items.filter((u) => {
      const ouPath = extractOuPathFromDn(u.dn || "");
      const groupsText = groupsByUser(u).join(" ");
      const fields = [
        u.sAMAccountName,
        u.displayName,
        u.givenName,
        u.sn,
        u.employeeID,
        u.employeeType,
        u.userPrincipalName,
        u.whenCreated,
        u.whenChanged,
        u.dn,
        ouPath,
        groupsText,
      ];
      return fields.some((value) => (value || "").toLowerCase().includes(kw));
    });
  }

  const sorted = [...items].sort((a, b) => {
    const diff = parseLdapTime(userUpdatedAt(b)) - parseLdapTime(userUpdatedAt(a));
    if (diff !== 0) return diff;
    const ua = String(a?.sAMAccountName || "").toLowerCase();
    const ub = String(b?.sAMAccountName || "").toLowerCase();
    return ua.localeCompare(ub);
  });
  return sorted;
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

function isOuExpanded(dn) {
  return expandedOuDns.value.has(normalizeDn(dn));
}

function collectOuDns(nodes, out = []) {
  for (const node of nodes || []) {
    out.push(normalizeDn(node.dn));
    collectOuDns(node.children || [], out);
  }
  return out;
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

function userUpdatedAt(user) {
  return user?.whenChanged || user?.whenCreated || "";
}

function parseLdapTime(value) {
  const raw = String(value || "").trim();
  if (!raw) return 0;

  // AD generalizedTime: YYYYMMDDHHMMSS(.0)Z
  const m = raw.match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\.\d+)?Z$/i);
  if (m) {
    const [, y, mo, d, h, mi, s] = m;
    return Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s));
  }

  const ts = Date.parse(raw);
  return Number.isFinite(ts) ? ts : 0;
}

function formatLdapTime(value) {
  const ts = parseLdapTime(value);
  if (!ts) return "-";
  return new Date(ts).toLocaleString();
}

function isProtectedUsername(username) {
  if (!username) return false;
  return protectedUsernames.has(String(username).toLowerCase());
}

function groupsByUser(user) {
  const key = normalizeDn(user?.dn || "");
  if (!key) return EMPTY_STR_LIST;
  return userGroupListMap.value.get(key) || EMPTY_STR_LIST;
}

function toggleGroup(cn, checked) {
  if (!cn) return;
  if (checked) {
    if (selectedGroups.value.includes(cn)) return;
    selectedGroups.value = [...selectedGroups.value, cn];
    return;
  }
  selectedGroups.value = selectedGroups.value.filter((x) => x !== cn);
}

function clearGroupFilters() {
  selectedGroups.value = [];
  groupKeyword.value = "";
  groupDropdownOpen.value = false;
}

function triggerImport() {
  importInputRef.value?.click();
}

function _downloadBlob(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "users-export.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

async function onExportUsers() {
  exporting.value = true;
  error.value = "";
  actionMessage.value = "";
  try {
    const { filename, blob } = await apiExportUsers();
    _downloadBlob(blob, filename);
    actionMessage.value = `Export completed: ${filename}`;
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    exporting.value = false;
  }
}

async function onImportFiles(event) {
  const input = event?.target;
  const files = Array.from(input?.files || []);
  if (!files.length) return;

  const confirmText = `Import ${files.length} file(s)? Existing same-name users will be skipped.`;
  if (!window.confirm(confirmText)) {
    if (input) input.value = "";
    return;
  }

  importing.value = true;
  error.value = "";
  actionMessage.value = "";
  try {
    const report = await apiImportUsers(files, {
      defaultGroupCn: "Students",
      passwordLength: 12,
    });
    importReport.value = report;
    actionMessage.value = `Import finished: created ${report.created}, skipped ${report.skipped}, failed ${report.failed}.`;
    await refreshAll();
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    importing.value = false;
    if (input) input.value = "";
  }
}

function openAddWindow() {
  window.open("/users/new", "_blank", "noopener,noreferrer");
}

function openEditWindow(user) {
  const username = resolveUsername(user);
  if (!username) return;
  window.open(`/users/edit/${encodeURIComponent(username)}`, "_blank", "noopener,noreferrer");
}

function clearOuFilter() {
  selectedOuDn.value = "";
  selectedOuPath.value = "";
}

function onRefreshUsers() {
  userKeyword.value = "";
  groupKeyword.value = "";
  selectedGroups.value = [];
  groupDropdownOpen.value = false;
  clearOuFilter();
  currentPage.value = 1;
  selectedUsernames.value = [];
  actionMessage.value = "";
  refreshAll();
}

function onRefreshTree() {
  ouKeyword.value = "";
  clearOuFilter();
  actionMessage.value = "";
  refreshOuTree();
}

function onExpandAllOu() {
  expandedOuDns.value = new Set(collectOuDns(ouTree.value));
}

function onCollapseAllOu() {
  expandedOuDns.value = new Set();
}

function onTreeLineClick(line) {
  if (!line || line.type !== "ou") return;
  // Switching OU should show that OU's users directly, without stale keyword filter.
  userKeyword.value = "";
  if (selectedOuDn.value.toLowerCase() === (line.dn || "").toLowerCase()) {
    clearOuFilter();
    return;
  }
  selectedOuDn.value = line.dn;
  selectedOuPath.value = line.path || "";
}

function onToggleOuExpand(line) {
  if (!line || line.type !== "ou" || !line.hasChildren) return;
  const dn = normalizeDn(line.dn);
  const next = new Set(expandedOuDns.value);
  if (next.has(dn)) next.delete(dn);
  else next.add(dn);
  expandedOuDns.value = next;
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
  await refreshAll();
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
    const nextTree = await apiListLdapOuTree();
    ouTree.value = nextTree;
    const allDns = new Set(collectOuDns(nextTree));
    const nextExpanded = new Set();
    for (const dn of expandedOuDns.value) {
      if (allDns.has(dn)) nextExpanded.add(dn);
    }
    for (const root of nextTree || []) {
      nextExpanded.add(normalizeDn(root.dn));
    }
    expandedOuDns.value = nextExpanded;
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loadingOuTree.value = false;
  }
}

async function refreshAll() {
  await Promise.all([refreshUsers(), refreshGroups(), refreshOuTree()]);
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
  await refreshAll();
}

function onClickOutside(event) {
  const target = event.target;
  if (!target.closest(".group-filter-inline")) groupDropdownOpen.value = false;
}

onMounted(async () => {
  window.addEventListener("message", onWindowMessage);
  document.addEventListener("click", onClickOutside);
  await refreshAll();
});

onUnmounted(() => {
  window.removeEventListener("message", onWindowMessage);
  document.removeEventListener("click", onClickOutside);
});

watch([userKeyword, selectedOuDn, selectedGroups, pageSize], () => {
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
.page-head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.file-input-hidden {
  display: none;
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
  grid-template-columns: minmax(255px, 0.66fr) minmax(0, 2.34fr);
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
.import-report {
  display: grid;
  gap: 8px;
}
.import-report-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}
.import-report-head h3 {
  margin: 0;
}
.import-table-wrap {
  overflow: auto;
  border: 1px solid #e6edf4;
  border-radius: 10px;
}
.import-table {
  width: 100%;
  min-width: 1000px;
  border-collapse: separate;
  border-spacing: 0;
}
.import-table th,
.import-table td {
  border-bottom: 1px solid #edf2f7;
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
  font-size: 13px;
}
.import-table th {
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #64748b;
  background: #f8fbff;
  position: sticky;
  top: 0;
  z-index: 1;
}
.import-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 66px;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 11px;
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  color: #334155;
  text-transform: lowercase;
}
.import-status.created {
  background: #dcfce7;
  border-color: #86efac;
  color: #14532d;
}
.import-status.skipped {
  background: #fef3c7;
  border-color: #fcd34d;
  color: #92400e;
}
.import-status.failed {
  background: #fee2e2;
  border-color: #fecaca;
  color: #991b1b;
}
.tree-panel,
.list-panel {
  height: 68vh;
  min-height: 520px;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
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
  gap: 8px;
  min-width: 0;
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
.tree-head-top {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
}
.tree-tools {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  flex-wrap: wrap;
  max-width: 100%;
}
.tree-tool-btn {
  height: 24px;
  min-width: 42px;
  padding: 0 8px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
}
.tree-search-row {
  display: block;
  min-width: 0;
  padding: 0;
}
.tree-search-input {
  display: block;
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box;
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
  box-sizing: border-box;
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
.active-filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.group-filter-inline {
  position: relative;
}
.group-dropdown-panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: min(420px, 78vw);
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  padding: 8px;
  display: grid;
  gap: 8px;
  z-index: 10;
}
.group-search-input {
  width: 100%;
  height: 34px;
  box-sizing: border-box;
  border: 1px solid #cfd8e3;
  border-radius: 8px;
  padding: 0 10px;
  outline: none;
}
.group-checkbox-list {
  max-height: 240px;
  overflow: auto;
  display: grid;
  gap: 4px;
}
.group-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  border-radius: 6px;
  font-size: 14px;
}
.group-option:hover {
  background: #f8fafc;
}
.group-panel-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.group-cell {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  max-width: 280px;
}
.group-chip {
  background: #f1f5f9;
  color: #334155;
  border: 1px solid #dbe3ef;
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 12px;
  line-height: 1.4;
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
  position: sticky;
  left: 0;
  z-index: 3;
  background: #fff;
}
.username-col {
  width: 160px;
  min-width: 160px;
  max-width: 160px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  position: sticky;
  left: 44px;
  z-index: 2;
  background: #fff;
}
.user-table th.check-col,
.user-table th.username-col {
  z-index: 5;
  background: #f8fbff;
}
.user-table tbody tr:hover .check-col,
.user-table tbody tr:hover .username-col {
  background: #f8fbff;
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
  cursor: default;
}
.tree-toggle {
  width: 16px;
  height: 16px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #64748b;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
}
.tree-toggle:hover {
  background: #e2e8f0;
}
.tree-toggle-placeholder {
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
}
.ou-row.clickable {
  cursor: pointer;
  border-radius: 8px;
  padding: 3px 6px;
}
.ou-row.clickable:hover {
  background: #f1f5f9;
}
.ou-row:not(.clickable) .main-text {
  color: #475569;
  font-weight: 500;
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
  font-size: 14px;
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
