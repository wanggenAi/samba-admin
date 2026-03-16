<template>
  <div class="users-page">
    <header class="page-head">
      <div>
        <h2>Users</h2>
        <p class="sub">Browse OU structure, filter users, and bulk-delete selected accounts. [DEPLOY SMOKE TEST]</p>
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
        <button
          v-if="canImport"
          class="btn"
          type="button"
          :disabled="importing"
          title="TXT only, max 2 MB per file, max 10 MB total"
          @click="triggerImport"
        >
          {{ importing ? "Importing..." : "Import TXT" }}
        </button>
        <span
          class="import-limit-help"
          tabindex="0"
          role="note"
          aria-label="Import limits"
          title="Import limits"
        >
          ?
          <span class="import-limit-tooltip" role="tooltip">
            TXT only. Max {{ importLimitPerFileText }} per file, max {{ importLimitTotalText }} total.
          </span>
        </span>
        <button v-if="canExport" class="btn" type="button" :disabled="exporting" @click="onExportUsers">
          {{ exporting ? "Exporting..." : "Export CSV" }}
        </button>
        <button v-if="canCreateUser" class="btn primary" type="button" @click="openAddWindow">New User</button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="actionMessage" class="ok">{{ actionMessage }}</p>
    <section v-if="importReport" class="panel import-report">
      <div class="import-report-head">
        <h3>Import Report</h3>
        <button class="btn" type="button" @click="closeImportReport">Close</button>
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
              <td class="mono" :class="{ 'is-empty-cell': !item.line_no }">{{ item.line_no || EMPTY_MARK }}</td>
              <td>
                <span class="import-status" :class="item.status">{{ item.status }}</span>
              </td>
              <td class="mono" :class="{ 'is-empty-cell': !hasValue(item.username) }">{{ item.username || EMPTY_MARK }}</td>
              <td class="mono" :class="{ 'is-empty-cell': !hasValue(item.password) }">{{ item.password || EMPTY_MARK }}</td>
              <td :class="{ 'is-empty-cell': !hasValue(importNameValue(item)) }">{{ importNameValue(item) || EMPTY_MARK }}</td>
              <td :class="{ 'is-empty-cell': !(item.ou_path?.length) }">{{ item.ou_path?.length ? item.ou_path.join(" > ") : EMPTY_MARK }}</td>
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

        <div class="tree-body-host" :class="{ loading: loadingOuTree }">
        <div v-if="!ouTreeLines.length" class="muted">No OU nodes found under current base DN.</div>
        <div v-else class="ou-tree-wrap">
          <div
            v-for="line in ouTreeLines"
            :key="line.key"
            class="ou-row"
            :class="{
              clickable: line.type === 'ou',
              active: line.type === 'ou' && isSelectedOuDn(line.dn),
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
          <DataLoadingOverlay :show="loadingOuTree" text="Loading OU tree..." />
        </div>
      </section>

      <section class="panel list-panel">
        <div class="panel-head list-head">
          <div class="head-left">
            <h3>User List</h3>
            <div class="active-filters">
              <div v-if="selectedOuDns.length" class="active-filter">
                <span class="muted">OU filter:</span>
                <code>{{ selectedOuFilterLabel }}</code>
                <button class="chip-clear-btn" type="button" @click="clearOuFilter">Clear</button>
              </div>
              <div v-if="selectedGroups.length" class="active-filter">
                <span class="muted">Group filter:</span>
                <code>{{ selectedGroups.join(", ") }}</code>
              </div>
            </div>
          </div>
          <div class="panel-actions list-actions">
            <button
              v-if="canDeleteUser"
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

        <div class="table-host" :class="{ loading: loadingUsers }">
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
                <th class="display-col">Display Name</th>
                <th class="username-col">Username</th>
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
                <td class="display-col" :class="{ 'is-empty-cell': !hasValue(u.displayName) }" :title="u.displayName || EMPTY_MARK">
                  {{ u.displayName || EMPTY_MARK }}
                </td>
                <td class="mono username-col" :class="{ 'is-empty-cell': !hasValue(u.sAMAccountName) }" :title="u.sAMAccountName || EMPTY_MARK">
                  {{ u.sAMAccountName || EMPTY_MARK }}
                </td>
                <td :class="{ 'is-empty-cell': !hasValue(u.givenName) }">{{ u.givenName || EMPTY_MARK }}</td>
                <td :class="{ 'is-empty-cell': !hasValue(u.sn) }">{{ u.sn || EMPTY_MARK }}</td>
                <td class="mono" :class="{ 'is-empty-cell': !hasValue(u.employeeID) }">{{ u.employeeID || EMPTY_MARK }}</td>
                <td class="mono" :class="{ 'is-empty-cell': !hasValue(u.employeeType) }">{{ u.employeeType || EMPTY_MARK }}</td>
                <td class="mono" :class="{ 'is-empty-cell': !hasValue(u.userPrincipalName) }">{{ u.userPrincipalName || EMPTY_MARK }}</td>
                <td class="mono" :class="{ 'is-empty-cell': !parseLdapTime(userUpdatedAt(u)) }">
                  {{ formatLdapTime(userUpdatedAt(u)) }}
                </td>
                <td>
                  <div class="group-cell" :class="{ expanded: isGroupsExpanded(u.dn) }">
                    <span
                      v-for="cn in visibleGroupsByUser(u)"
                      :key="`${u.dn}:${cn}`"
                      class="group-chip"
                      :title="cn"
                    >
                      {{ cn }}
                    </span>
                    <span v-if="!groupsByUser(u).length" class="empty-mark">{{ EMPTY_MARK }}</span>
                    <button
                      v-if="hasMoreGroups(u)"
                      type="button"
                      class="cell-more-btn"
                      @click.stop="toggleGroupsExpanded(u.dn)"
                    >
                      {{ isGroupsExpanded(u.dn) ? "Less" : `+${hiddenGroupCount(u)} more` }}
                    </button>
                  </div>
                </td>
                <td class="dn mono" :class="{ expanded: isDnExpanded(u.dn) }" :title="u.dn">
                  <span class="dn-text">{{ u.dn }}</span>
                  <button
                    v-if="u.dn && u.dn.length > 42"
                    type="button"
                    class="cell-more-btn dn-more-btn"
                    @click.stop="toggleDnExpanded(u.dn)"
                  >
                    {{ isDnExpanded(u.dn) ? "Less" : "More" }}
                  </button>
                </td>
                <td>
                  <button
                    v-if="canEditUser"
                    class="btn"
                    type="button"
                    @click.stop="openEditWindow(u)"
                  >
                    Edit
                  </button>
                </td>
              </tr>
              <tr v-if="!users.length" class="empty-row">
                <td colspan="12" class="muted">No users found.</td>
              </tr>
            </tbody>
            </table>
          </div>
          <DataLoadingOverlay :show="loadingUsers" text="Loading users..." />
        </div>

        <div class="pager" v-if="totalUsers">
          <div class="pager-block pager-summary">
            <span class="muted">Total</span>
            <strong>{{ totalUsers }}</strong>
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
            <button class="btn pager-btn" :disabled="loadingUsers || currentPage <= 1" @click="goPrevPage">Prev</button>
            <span class="page-indicator">Page {{ currentPage }} / {{ totalPages }}</span>
            <button class="btn pager-btn" :disabled="loadingUsers || currentPage >= totalPages" @click="goNextPage">
              Next
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import DataLoadingOverlay from "../../components/DataLoadingOverlay.vue";
import { useAuthStore } from "../../auth/store";
import {
  apiDeleteUser,
  apiExportUsers,
  apiImportUsers,
  apiListLdapGroups,
  apiListLdapOuTree,
  apiListLdapUsersPage,
} from "../../api/client";

const auth = useAuthStore();
const canCreateUser = computed(() => auth.hasPermission("users.create"));
const canEditUser = computed(() => auth.hasPermission("users.edit"));
const canDeleteUser = computed(() => auth.hasPermission("users.delete"));
const canImport = computed(() => auth.hasPermission("users.import"));
const canExport = computed(() => auth.hasPermission("users.export"));

const users = shallowRef([]);
const totalUsers = ref(0);
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
const selectedOuDns = ref([]);
const currentPage = ref(1);
const pageSize = ref(10);
const deletingBatch = ref(false);
const selectedUsernames = ref([]);
const expandedOuDns = ref(new Set());
const expandedGroupUserDns = ref(new Set());
const expandedDnUserDns = ref(new Set());
const protectedUsernames = new Set(["krbtgt"]);
const importInputRef = ref(null);
const usersRequestSeq = ref(0);
const suppressUsersFilterWatch = ref(false);
const EMPTY_STR_LIST = Object.freeze([]);
const EMPTY_MARK = "-";
const GROUPS_COLLAPSED_COUNT = 2;
const MAX_IMPORT_FILE_BYTES = 2 * 1024 * 1024;
const MAX_IMPORT_TOTAL_BYTES = 10 * 1024 * 1024;
const importLimitPerFileText = `${(MAX_IMPORT_FILE_BYTES / (1024 * 1024)).toFixed(0)} MB`;
const importLimitTotalText = `${(MAX_IMPORT_TOTAL_BYTES / (1024 * 1024)).toFixed(0)} MB`;
const selectedOuDnKeySet = computed(() => new Set(selectedOuDns.value.map((dn) => normalizeDn(dn))));
const selectedOuFilterLabel = computed(() => {
  const paths = selectedOuDns.value
    .map((dn) => extractOuPathFromDn(dn))
    .filter((x) => x);
  if (!paths.length) return "";
  if (paths.length <= 2) return paths.join(", ");
  return `${paths.slice(0, 2).join(", ")} +${paths.length - 2} more`;
});

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

const filteredGroups = computed(() => {
  const kw = groupKeyword.value.toLowerCase();
  if (!kw) return groups.value.slice(0, 100);
  return groups.value.filter((g) => (g.cn || "").toLowerCase().includes(kw)).slice(0, 100);
});

const totalPages = computed(() => {
  return Math.max(1, Math.ceil(totalUsers.value / pageSize.value));
});

const paginatedUsers = computed(() => {
  return users.value;
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

function compactOuTreeNodes(nodes) {
  return (nodes || []).map((node) => ({
    ou: String(node?.ou || ""),
    dn: String(node?.dn || ""),
    users: (node?.users || []).map((u) => ({
      dn: String(u?.dn || ""),
      sAMAccountName: String(u?.sAMAccountName || ""),
      displayName: String(u?.displayName || ""),
    })),
    children: compactOuTreeNodes(node?.children || []),
  }));
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

function hasValue(value) {
  return String(value ?? "").trim().length > 0;
}

function importNameValue(item) {
  return [item?.first_name, item?.last_name].filter((v) => hasValue(v)).join(" ").trim();
}

function formatLdapTime(value) {
  const ts = parseLdapTime(value);
  if (!ts) return EMPTY_MARK;
  return new Date(ts).toLocaleString();
}

function isProtectedUsername(username) {
  if (!username) return false;
  return protectedUsernames.has(String(username).toLowerCase());
}

function groupsByUser(user) {
  const values = Array.isArray(user?.groups) ? user.groups : EMPTY_STR_LIST;
  return values;
}

function isGroupsExpanded(dn) {
  return expandedGroupUserDns.value.has(String(dn || ""));
}

function toggleGroupsExpanded(dn) {
  const key = String(dn || "");
  if (!key) return;
  const next = new Set(expandedGroupUserDns.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expandedGroupUserDns.value = next;
}

function visibleGroupsByUser(user) {
  const all = groupsByUser(user);
  if (isGroupsExpanded(user?.dn)) return all;
  return all.slice(0, GROUPS_COLLAPSED_COUNT);
}

function hiddenGroupCount(user) {
  const all = groupsByUser(user);
  return Math.max(0, all.length - GROUPS_COLLAPSED_COUNT);
}

function hasMoreGroups(user) {
  return hiddenGroupCount(user) > 0;
}

function isDnExpanded(dn) {
  return expandedDnUserDns.value.has(String(dn || ""));
}

function toggleDnExpanded(dn) {
  const key = String(dn || "");
  if (!key) return;
  const next = new Set(expandedDnUserDns.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expandedDnUserDns.value = next;
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
  if (!canImport.value) return;
  importInputRef.value?.click();
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(2)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

function closeImportReport() {
  const report = importReport.value;
  if (report && Array.isArray(report.results)) {
    // Explicitly clear large row buffers before dropping the reference.
    report.results.length = 0;
  }
  importReport.value = null;
  actionMessage.value = "";
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
  if (!canExport.value) return;
  exporting.value = true;
  error.value = "";
  actionMessage.value = "";
  try {
    const { filename, blob } = await apiExportUsers({
      keyword: userKeyword.value,
      ouDns: selectedOuDns.value,
      groupCns: selectedGroups.value,
    });
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

  const oversizedFiles = files.filter((f) => (f?.size || 0) > MAX_IMPORT_FILE_BYTES);
  if (oversizedFiles.length) {
    const names = oversizedFiles.map((f) => `${f.name} (${formatBytes(f.size)})`).join(", ");
    error.value = `Import blocked: file exceeds ${formatBytes(MAX_IMPORT_FILE_BYTES)} limit. ${names}`;
    if (input) input.value = "";
    return;
  }

  const totalBytes = files.reduce((sum, f) => sum + (f?.size || 0), 0);
  if (totalBytes > MAX_IMPORT_TOTAL_BYTES) {
    error.value = `Import blocked: total size ${formatBytes(totalBytes)} exceeds ${formatBytes(MAX_IMPORT_TOTAL_BYTES)}.`;
    if (input) input.value = "";
    return;
  }

  const confirmText = `Import ${files.length} file(s)? Existing same-name users will be skipped.`;
  if (!window.confirm(confirmText)) {
    if (input) input.value = "";
    return;
  }

  importing.value = true;
  error.value = "";
  actionMessage.value = "";
  closeImportReport();
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
  if (!canCreateUser.value) return;
  window.open("/users/new", "_blank", "noopener,noreferrer");
}

function openEditWindow(user) {
  if (!canEditUser.value) return;
  const username = resolveUsername(user);
  if (!username) return;
  window.open(`/users/edit/${encodeURIComponent(username)}`, "_blank", "noopener,noreferrer");
}

function clearOuFilter() {
  selectedOuDns.value = [];
}

function isSelectedOuDn(dn) {
  const key = normalizeDn(dn);
  return selectedOuDnKeySet.value.has(key);
}

function toggleSelectedOuDn(dn) {
  const key = normalizeDn(dn);
  if (!key) return;
  const next = [...selectedOuDns.value];
  const idx = next.findIndex((x) => normalizeDn(x) === key);
  if (idx >= 0) next.splice(idx, 1);
  else next.push(String(dn || "").trim());
  selectedOuDns.value = next;
}

function onRefreshUsers() {
  suppressUsersFilterWatch.value = true;
  userKeyword.value = "";
  groupKeyword.value = "";
  selectedGroups.value = [];
  groupDropdownOpen.value = false;
  clearOuFilter();
  currentPage.value = 1;
  selectedUsernames.value = [];
  actionMessage.value = "";
  Promise.resolve().then(() => {
    suppressUsersFilterWatch.value = false;
    refreshUsers();
  });
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
  toggleSelectedOuDn(line.dn);
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
  if (!canDeleteUser.value) return;
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
  await refreshUsers();
  refreshOuTree(false);
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
  const seq = usersRequestSeq.value + 1;
  usersRequestSeq.value = seq;
  loadingUsers.value = true;
  error.value = "";
  try {
    const payload = await apiListLdapUsersPage({
      view: "list",
      page: currentPage.value,
      pageSize: pageSize.value,
      keyword: userKeyword.value,
      ouDns: selectedOuDns.value,
      groupCns: selectedGroups.value,
    });
    if (seq !== usersRequestSeq.value) return;
    totalUsers.value = Number(payload?.total || 0);
    users.value = (payload?.items || []).map((u) => ({
      dn: String(u?.dn || ""),
      sAMAccountName: String(u?.sAMAccountName || ""),
      displayName: String(u?.displayName || ""),
      givenName: String(u?.givenName || ""),
      sn: String(u?.sn || ""),
      employeeID: String(u?.employeeID || ""),
      employeeType: String(u?.employeeType || ""),
      userPrincipalName: String(u?.userPrincipalName || ""),
      whenCreated: String(u?.whenCreated || ""),
      whenChanged: String(u?.whenChanged || ""),
      groups: Array.isArray(u?.groups) ? u.groups.map((x) => String(x || "").trim()).filter(Boolean) : [],
    }));
    selectedUsernames.value = selectedUsernames.value.filter((name) =>
      users.value.some((u) => resolveUsername(u) === name)
    );
  } catch (e) {
    if (seq !== usersRequestSeq.value) return;
    error.value = e?.message || String(e);
  } finally {
    if (seq === usersRequestSeq.value) loadingUsers.value = false;
  }
}

async function refreshGroups() {
  loadingGroups.value = true;
  error.value = "";
  try {
    const groupsPayload = await apiListLdapGroups({ includeMembers: false, includeDescription: false });
    const nextGroups = [];
    const seenGroupCns = new Set();

    for (const g of groupsPayload || []) {
      const cn = String(g?.cn || "").trim();
      if (!cn) continue;

      if (!seenGroupCns.has(cn)) {
        seenGroupCns.add(cn);
        nextGroups.push({ cn });
      }
    }

    nextGroups.sort((a, b) => a.cn.localeCompare(b.cn));
    groups.value = nextGroups;
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loadingGroups.value = false;
  }
}

async function refreshOuTree(showLoading = true) {
  if (showLoading) loadingOuTree.value = true;
  error.value = "";
  try {
    const payload = await apiListLdapOuTree({ includeUsers: true, userView: "tree" });
    const nextTree = compactOuTreeNodes(payload);
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
    if (showLoading) loadingOuTree.value = false;
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
  if (!event.data) return;
  if (event.data.type === "USER_CREATED_OR_UPDATED") {
    actionMessage.value = `Saved user: ${event.data.username || EMPTY_MARK}`;
  } else if (event.data.type !== "USER_EDITOR_CLOSED") {
    return;
  }
  await refreshUsers();
  refreshOuTree(false);
}

function onClickOutside(event) {
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (!target.closest(".group-filter-inline")) groupDropdownOpen.value = false;
}

onMounted(async () => {
  window.addEventListener("message", onWindowMessage);
  document.addEventListener("click", onClickOutside);
  await refreshUsers();
  void Promise.allSettled([refreshGroups(), refreshOuTree()]);
});

onUnmounted(() => {
  window.removeEventListener("message", onWindowMessage);
  document.removeEventListener("click", onClickOutside);
  closeImportReport();
  if (importInputRef.value) importInputRef.value.value = "";
  users.value = [];
  totalUsers.value = 0;
  groups.value = [];
  ouTree.value = [];
  selectedUsernames.value = [];
  expandedGroupUserDns.value = new Set();
  expandedDnUserDns.value = new Set();
  expandedOuDns.value = new Set();
});

watch([userKeyword, selectedOuDns, selectedGroups, pageSize], () => {
  if (suppressUsersFilterWatch.value) return;
  if (currentPage.value !== 1) {
    currentPage.value = 1;
    return;
  }
  refreshUsers();
});

watch(currentPage, () => {
  if (suppressUsersFilterWatch.value) return;
  refreshUsers();
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
.import-limit-help {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid #d3dde8;
  border-radius: 999px;
  background: #f8fafc;
  color: #475569;
  font-weight: 700;
  font-size: 14px;
  cursor: help;
  user-select: none;
  line-height: 1;
}
.import-limit-help:hover,
.import-limit-help:focus-visible {
  background: #eef2f7;
}
.import-limit-tooltip {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: min(280px, 78vw);
  padding: 8px 10px;
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #ffffff;
  color: #475569;
  font-size: 12px;
  line-height: 1.4;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12);
  z-index: 20;
  opacity: 0;
  transform: translateY(-4px);
  pointer-events: none;
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.import-limit-help:hover .import-limit-tooltip,
.import-limit-help:focus-visible .import-limit-tooltip {
  opacity: 1;
  transform: translateY(0);
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
  height: 76vh;
  min-height: 620px;
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
.chip-clear-btn {
  border: 1px solid #cbd5e1;
  background: #ffffff;
  color: #0f172a;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 12px;
  line-height: 1.4;
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
  flex-wrap: nowrap;
  max-width: 200px;
  overflow: hidden;
  white-space: nowrap;
  align-items: center;
}
.group-cell.expanded {
  flex-wrap: wrap;
  max-width: 260px;
  white-space: normal;
}
.group-chip {
  background: #f1f5f9;
  color: #334155;
  border: 1px solid #dbe3ef;
  border-radius: 999px;
  padding: 0 7px;
  font-size: 13px;
  line-height: 1.4;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cell-more-btn {
  border: none;
  background: transparent;
  color: #2563eb;
  font-size: 13px;
  font-weight: 600;
  padding: 0 2px;
  cursor: pointer;
  line-height: 1.3;
  white-space: nowrap;
}
.cell-more-btn:hover {
  text-decoration: underline;
}
.empty-mark {
  display: inline-block;
  min-width: 1ch;
  text-align: center;
  font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  color: #94a3b8;
}
.is-empty-cell {
  font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif !important;
  color: #94a3b8;
}
.table-wrap {
  height: 100%;
  overflow: auto;
  border: 1px solid #e6edf4;
  border-radius: 12px;
  background: #fff;
  max-height: none;
}
.table-host {
  position: relative;
  flex: 1;
  min-height: 120px;
}
.table-host.loading {
  pointer-events: none;
}
.tree-body-host {
  position: relative;
  min-height: 120px;
}
.tree-body-host.loading {
  pointer-events: none;
}
.user-table {
  width: 100%;
  min-width: 1020px;
  border-collapse: separate;
  border-spacing: 0;
}
.user-table th,
.user-table td {
  border-bottom: 1px solid #edf2f7;
  padding: 8px 9px;
  text-align: left;
  vertical-align: top;
  font-size: 13px;
}
.user-table th {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
  color: #64748b;
  background: #f8fbff;
  position: sticky;
  top: 0;
  z-index: 1;
}
.check-col {
  width: 38px;
  text-align: center !important;
  position: sticky;
  left: 0;
  z-index: 3;
  background: #fff;
}
.display-col {
  width: 220px;
  min-width: 220px;
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  word-break: break-word;
  overflow-wrap: anywhere;
  position: sticky;
  left: 38px;
  z-index: 2;
  background: #fff;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: 0.01em;
  line-height: 1.3;
}
.username-col {
  width: 160px;
  min-width: 160px;
  max-width: 160px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.user-table th.check-col,
.user-table th.display-col {
  z-index: 5;
  background: #f8fbff;
}
.user-table tbody tr:hover .check-col,
.user-table tbody tr:hover .display-col {
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
  font-size: 11px;
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
  max-width: 360px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #475569;
}
.dn .dn-text {
  display: inline-block;
  max-width: calc(100% - 42px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
.dn.expanded {
  white-space: normal;
}
.dn.expanded .dn-text {
  max-width: 100%;
  white-space: normal;
  word-break: break-all;
}
.dn-more-btn {
  margin-left: 6px;
  vertical-align: middle;
}
.user-table td .btn {
  height: 32px;
  padding: 0 11px;
  font-size: 13px;
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
