<template>
  <div class="dashboard-page">
    <header class="page-head">
      <div>
        <h2>Dashboard</h2>
        <p class="sub">User login/logout timeline from LDAP attributes (`lastLogon` / `lastLogoff`).</p>
      </div>
      <div class="page-head-actions">
        <button class="btn" type="button" :disabled="loading" @click="refreshAll">
          {{ loading ? "Loading..." : "Refresh" }}
        </button>
        <button class="btn" type="button" @click="autoScrollEnabled = !autoScrollEnabled">
          {{ autoScrollEnabled ? "Pause Scroll" : "Start Scroll" }}
        </button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <section class="stats-grid">
      <article class="stat-card total">
        <div class="stat-label">Total Users</div>
        <div class="stat-value">{{ allUsersTotal }}</div>
      </article>
      <article class="stat-card recent">
        <div class="stat-label">Logged In (Last 3 Days)</div>
        <div class="stat-value">{{ recent3DaysLoginCount }}</div>
      </article>
      <article class="stat-card status">
        <div class="stat-label">LDAP Status</div>
        <div class="stat-value status-value">
          <span class="dot" :class="{ ok: status?.ok, bad: status && !status.ok }"></span>
          {{ status?.ok ? "Connected" : "Unknown" }}
        </div>
      </article>
    </section>

    <section class="panel">
      <div class="filters">
        <input
          v-model.trim="keyword"
          class="search-input"
          type="text"
          placeholder="Search username / display name / UPN / OU / group / time"
        />
        <span class="time-filter-label">Logon From</span>
        <input
          v-model="loginFrom"
          class="datetime-input"
          type="datetime-local"
          aria-label="Login from (lastLogon)"
          title="Login from (lastLogon)"
        />
        <span class="time-filter-label">To</span>
        <input
          v-model="loginTo"
          class="datetime-input"
          type="datetime-local"
          aria-label="Login to (lastLogon)"
          title="Login to (lastLogon)"
        />

        <div class="ou-filter-inline">
          <button
            class="btn ou-trigger-btn"
            type="button"
            :disabled="loading"
            @click="toggleOuDropdown"
          >
            {{ selectedOuLabel }}
          </button>
          <div v-if="ouDropdownOpen" class="ou-dropdown-panel">
            <input
              v-model.trim="ouKeyword"
              type="text"
              class="ou-search-input"
              placeholder="Search OU by name / path / DN"
            />
            <button
              class="btn ou-all-btn"
              type="button"
              :class="{ active: !selectedOuDns.length }"
              @click="clearOuFilter"
            >
              All OUs
            </button>
            <div class="ou-tree-picker">
              <div
                v-for="line in ouTreeLines"
                :key="line.key"
                class="ou-row"
                :class="{ active: isOuSelected(line.dn) }"
                :style="{ paddingLeft: `${line.depth * 16}px` }"
              >
                <button
                  v-if="line.hasChildren"
                  type="button"
                  class="tree-toggle"
                  :aria-label="line.expanded ? 'Collapse OU' : 'Expand OU'"
                  @click.stop="toggleOuExpand(line)"
                >
                  {{ line.expanded ? "▾" : "▸" }}
                </button>
                <span v-else class="tree-toggle-placeholder" aria-hidden="true"></span>
                <button
                  type="button"
                  class="ou-row-btn"
                  :title="line.dn"
                  @click="selectOu(line)"
                >
                  <input
                    type="checkbox"
                    class="ou-row-check"
                    :checked="isOuSelected(line.dn)"
                    @click.stop
                    @change.stop="toggleOuSelection(line.dn)"
                  />
                  <span class="ou-tag">OU</span>
                  <span class="ou-name">{{ line.ou }}</span>
                </button>
              </div>
              <div v-if="loadingOuTree" class="muted small-gap">Loading OUs...</div>
              <div v-if="!ouTreeLines.length" class="muted small-gap">No OU matched.</div>
            </div>
            <div v-if="selectedOuHitRows.length" class="ou-hit-summary">
              <div class="muted">Current page hits by selected OU:</div>
              <div class="ou-hit-list">
                <span v-for="row in selectedOuHitRows" :key="row.dnKey" class="ou-hit-chip">
                  {{ row.label }}: {{ row.hits }}
                </span>
              </div>
            </div>
            <div class="ou-panel-actions">
              <button class="btn" type="button" :disabled="!selectedOuDns.length" @click="clearOuFilter">Clear</button>
              <button class="btn" type="button" @click="ouDropdownOpen = false">Done</button>
            </div>
          </div>
        </div>

        <div class="group-filter-inline">
          <button
            class="btn"
            type="button"
            :disabled="loading"
            @click="toggleGroupDropdown"
          >
            Groups ({{ selectedGroups.length }})
          </button>
          <div v-if="groupDropdownOpen" class="group-dropdown-panel">
            <input
              v-model.trim="groupKeyword"
              class="group-search-input"
              type="text"
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
              <div v-if="loadingGroups" class="muted">Loading groups...</div>
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

        <button class="btn" type="button" @click="resetFilters">Reset Filters</button>
      </div>

      <div
        class="table-wrap"
        :class="{ autoscroll: autoScrollEnabled, loading }"
        ref="tableWrapRef"
        @wheel="onTableWheel"
      >
        <table class="log-table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Display Name</th>
              <th>UPN</th>
              <th>OU Path</th>
              <th>Groups</th>
              <th>Last Logon</th>
              <th>Last Logoff</th>
              <th>Latest Activity (Desc)</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(u, idx) in renderedUsers"
              :key="`${u.dn}:${idx}`"
              ref="logRowRefs"
              class="log-row"
              :class="rowStripeClass(idx)"
            >
              <td class="mono user-col">
                <span class="user-chip" :class="{ 'is-empty-cell': !hasValue(u.sAMAccountName) }">
                  {{ u.sAMAccountName || EMPTY_MARK }}
                </span>
              </td>
              <td :class="{ 'is-empty-cell': !hasValue(displayNameValue(u)) }">
                {{ displayNameValue(u) || EMPTY_MARK }}
              </td>
              <td class="mono" :class="{ 'is-empty-cell': !hasValue(u.userPrincipalName) }">
                {{ u.userPrincipalName || EMPTY_MARK }}
              </td>
              <td :class="{ 'is-empty-cell': !hasValue(ouPathValue(u)) }">{{ ouPathValue(u) || EMPTY_MARK }}</td>
              <td>
                <div class="group-cell">
                  <span
                    v-for="cn in groupsByUser(u)"
                    :key="`${u.dn}:${cn}`"
                    class="group-chip"
                  >
                    {{ cn }}
                  </span>
                  <span v-if="!groupsByUser(u).length" class="empty-mark">{{ EMPTY_MARK }}</span>
                </div>
              </td>
              <td class="mono time-cell" :class="{ 'time-empty': !parseLdapTimestamp(u.lastLogon) }">
                {{ formatLdapTimestamp(u.lastLogon) }}
              </td>
              <td class="mono time-cell" :class="{ 'time-empty': !parseLdapTimestamp(u.lastLogoff) }">
                {{ formatLdapTimestamp(u.lastLogoff) }}
              </td>
              <td class="mono">
                <span class="activity-chip" :class="activityToneClass(u)">
                  {{ formatTimestampMs(latestActivityTs(u)) }}
                </span>
              </td>
            </tr>
            <tr v-if="!users.length" class="empty-row">
              <td colspan="8" class="muted">No users found.</td>
            </tr>
          </tbody>
        </table>
        <DataLoadingOverlay :show="loading" text="Loading users..." />
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
            <select v-model.number="pageSize" class="select small">
              <option :value="10">10</option>
              <option :value="20">20</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
            </select>
          </label>
        </div>

        <div class="pager-block pager-nav">
          <button class="btn pager-btn" :disabled="loading || currentPage <= 1" @click="goPrevPage">Prev</button>
          <span class="page-indicator">Page {{ currentPage }} / {{ totalPages }}</span>
          <button class="btn pager-btn" :disabled="loading || currentPage >= totalPages" @click="goNextPage">Next</button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import DataLoadingOverlay from "../../components/DataLoadingOverlay.vue";
import {
  apiLdapDashboardSummary,
  apiLdapHealth,
  apiListLdapGroups,
  apiListLdapOuTree,
  apiListLdapUsersPage,
} from "../../api/client";

const users = shallowRef([]);
const groups = shallowRef([]);
const ouTree = shallowRef([]);
const status = ref(null);
const loading = ref(false);
const error = ref("");
const usersRequestSeq = ref(0);
const totalUsers = ref(0);
const allUsersTotal = ref(0);
const recent3DaysLoginCount = ref(0);

const keyword = ref("");
const loginFrom = ref("");
const loginTo = ref("");
const selectedOuDns = ref([]);
const selectedGroups = ref([]);
const groupKeyword = ref("");
const groupDropdownOpen = ref(false);
const loadingGroups = ref(false);
const groupsLoaded = ref(false);

const ouKeyword = ref("");
const ouDropdownOpen = ref(false);
const loadingOuTree = ref(false);
const ouTreeLoaded = ref(false);
const expandedOuDns = ref(new Set());

const currentPage = ref(1);
const pageSize = ref(20);

const tableWrapRef = ref(null);
const logRowRefs = ref([]);
const autoScrollEnabled = ref(true);
let autoScrollTimer = null;
let refreshTimer = null;
const EMPTY_STR_LIST = Object.freeze([]);
const EMPTY_MARK = "-";
const AUTO_SCROLL_STEP_PX = 1;
const AUTO_SCROLL_INTERVAL_MS = 28;
const seamlessLoopHeightPx = ref(0);

const selectedOuDnKeySet = computed(() => new Set(selectedOuDns.value.map((dn) => normalizeDn(dn))));

const ouPathMap = computed(() => {
  const out = new Map();
  const walk = (nodes, path = []) => {
    for (const node of nodes || []) {
      const nextPath = [...path, node.ou];
      out.set(normalizeDn(node.dn), nextPath.join(" > "));
      walk(node.children || [], nextPath);
    }
  };
  walk(ouTree.value);
  return out;
});

const selectedOuLabel = computed(() => {
  const count = selectedOuDns.value.length;
  if (!count) return "OU: All OUs";
  if (count === 1) {
    const key = normalizeDn(selectedOuDns.value[0]);
    const label = ouPathMap.value.get(key) || selectedOuDns.value[0];
    return `OU: ${label}`;
  }
  return `OU: ${count} selected`;
});

const selectedOuHitRows = computed(() => {
  if (!selectedOuDns.value.length) return [];
  const targets = selectedOuDns.value.map((dn) => ({
    dnRaw: String(dn || "").trim(),
    dnKey: normalizeDn(dn),
  }));
  const rows = targets.map((target) => {
    let hits = 0;
    for (const user of users.value || []) {
      const parent = normalizeDn(parentDnOfUser(user?.dn || ""));
      if (!parent) continue;
      if (parent === target.dnKey || parent.endsWith(`,${target.dnKey}`)) hits += 1;
    }
    return {
      dnKey: target.dnKey,
      label: ouPathMap.value.get(target.dnKey) || target.dnRaw,
      hits,
    };
  });
  rows.sort((a, b) => a.label.localeCompare(b.label));
  return rows;
});

const ouTreeLines = computed(() => {
  const kw = ouKeyword.value.trim().toLowerCase();

  const collect = (nodes, depth, path) => {
    const lines = [];
    let matchedAny = false;

    for (const node of nodes || []) {
      const currentPath = [...path, node.ou];
      const pathText = currentPath.join(" > ");
      const childRes = collect(node.children || [], depth + 1, currentPath);
      const dnKey = normalizeDn(node.dn);
      const expanded = isOuExpanded(node.dn);

      const nodeHit = !kw || [node.ou, node.dn, pathText].some((v) => String(v || "").toLowerCase().includes(kw));
      const matched = nodeHit || childRes.matched;

      if (matched) {
        lines.push({
          key: `ou:${dnKey}`,
          dn: node.dn,
          dnKey,
          ou: node.ou,
          depth,
          path: pathText,
          hasChildren: (node.children || []).length > 0,
          expanded,
        });

        if (kw || expanded) {
          lines.push(...childRes.lines);
        }
      }

      matchedAny = matchedAny || matched;
    }

    return { lines, matched: matchedAny };
  };

  return collect(ouTree.value, 0, []).lines;
});

const filteredGroups = computed(() => {
  const kw = groupKeyword.value.trim().toLowerCase();
  if (!kw) return groups.value.slice(0, 120);
  return groups.value.filter((g) => (g.cn || "").toLowerCase().includes(kw)).slice(0, 120);
});

const totalPages = computed(() => Math.max(1, Math.ceil(totalUsers.value / pageSize.value)));
const paginatedUsers = computed(() => users.value);

const seamlessScrollActive = computed(() => autoScrollEnabled.value && paginatedUsers.value.length > 1);

const renderedUsers = computed(() => {
  const pageRows = paginatedUsers.value;
  if (!seamlessScrollActive.value) return pageRows;
  // Duplicate rows once to support loop-reset without visible jump.
  return pageRows.concat(pageRows);
});

function rowStripeClass(renderedIndex) {
  const baseLen = paginatedUsers.value.length;
  if (!baseLen) return "stripe-odd";
  const baseIndex = renderedIndex % baseLen;
  return baseIndex % 2 === 0 ? "stripe-odd" : "stripe-even";
}

async function recomputeSeamlessLoopHeight() {
  await nextTick();
  const rows = Array.isArray(logRowRefs.value) ? logRowRefs.value : [];
  if (!seamlessScrollActive.value) {
    seamlessLoopHeightPx.value = 0;
    return;
  }

  const half = paginatedUsers.value.length;
  if (half < 2 || rows.length < half + 1) {
    seamlessLoopHeightPx.value = 0;
    return;
  }

  const first = rows[0];
  const secondStart = rows[half];
  if (!(first instanceof HTMLElement) || !(secondStart instanceof HTMLElement)) {
    seamlessLoopHeightPx.value = 0;
    return;
  }

  const loopHeight = secondStart.offsetTop - first.offsetTop;
  seamlessLoopHeightPx.value = loopHeight > 0 ? loopHeight : 0;

  const wrap = tableWrapRef.value;
  if (wrap && seamlessLoopHeightPx.value > 0 && wrap.scrollTop >= seamlessLoopHeightPx.value) {
    wrap.scrollTop = wrap.scrollTop % seamlessLoopHeightPx.value;
  }
}

function normalizeDn(dn) {
  return String(dn || "")
    .split(",")
    .map((p) => p.trim().toLowerCase())
    .filter(Boolean)
    .join(",");
}

function formatOuPathFromDn(dn) {
  const raw = String(dn || "");
  if (!raw) return "";
  const ous = [];
  for (const part of raw.split(",")) {
    const p = part.trim();
    if (p.toUpperCase().startsWith("OU=")) {
      ous.push(p.slice(3));
    }
  }
  return ous.reverse().join(" > ");
}

function parentDnOfUser(dn) {
  const raw = String(dn || "");
  const idx = raw.indexOf(",");
  if (idx < 0) return "";
  return raw.slice(idx + 1);
}

function hasValue(value) {
  return String(value ?? "").trim().length > 0;
}

function displayNameValue(user) {
  const direct = String(user?.displayName || "").trim();
  if (direct) return direct;
  return [user?.givenName, user?.sn].filter((v) => hasValue(v)).join(" ").trim();
}

function ouPathValue(user) {
  return formatOuPathFromDn(user?.dn || "");
}

function groupsByUser(user) {
  const values = Array.isArray(user?.groups) ? user.groups : EMPTY_STR_LIST;
  return values;
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

function clearOuFilter() {
  selectedOuDns.value = [];
}

function resetFilters() {
  keyword.value = "";
  loginFrom.value = "";
  loginTo.value = "";
  selectedOuDns.value = [];
  ouKeyword.value = "";
  clearGroupFilters();
  currentPage.value = 1;
}

function collectOuDns(nodes, out = []) {
  for (const node of nodes || []) {
    out.push(normalizeDn(node.dn));
    collectOuDns(node.children || [], out);
  }
  return out;
}

function isOuExpanded(dn) {
  return expandedOuDns.value.has(normalizeDn(dn));
}

function toggleOuExpand(line) {
  if (!line?.hasChildren) return;
  const next = new Set(expandedOuDns.value);
  if (next.has(line.dnKey)) next.delete(line.dnKey);
  else next.add(line.dnKey);
  expandedOuDns.value = next;
}

function selectOu(line) {
  if (!line) return;
  toggleOuSelection(line.dn);
}

function isOuSelected(dn) {
  const key = normalizeDn(dn);
  return selectedOuDnKeySet.value.has(key);
}

function toggleOuSelection(dn) {
  const key = normalizeDn(dn);
  if (!key) return;
  const next = [...selectedOuDns.value];
  const idx = next.findIndex((x) => normalizeDn(x) === key);
  if (idx >= 0) {
    next.splice(idx, 1);
  } else {
    next.push(String(dn || "").trim());
  }
  selectedOuDns.value = next;
}

function parseInputDateTime(value) {
  const raw = String(value || "").trim();
  if (!raw) return 0;
  const ts = Date.parse(raw);
  if (!Number.isFinite(ts)) return 0;
  return ts > 0 ? ts : 0;
}

function parseLdapTimestamp(value) {
  const raw = String(value || "").trim();
  if (!raw) return 0;

  if (/^\d+$/.test(raw)) {
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) return 0;

    // AD filetime (100ns intervals since 1601-01-01 UTC)
    if (n > 100000000000000) {
      const ms = Math.floor(n / 10000 - 11644473600000);
      return ms > 0 ? ms : 0;
    }

    // unix milliseconds
    if (n > 1000000000000) return n;

    // unix seconds
    if (n > 1000000000) return n * 1000;
    return 0;
  }

  // AD generalizedTime: YYYYMMDDHHMMSS(.0)Z
  const generalized = raw.match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\.\d+)?Z$/i);
  if (generalized) {
    const [, y, mo, d, h, mi, s] = generalized;
    const ts = Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s));
    return ts > 0 ? ts : 0;
  }

  let ts = Date.parse(raw);
  if (!Number.isFinite(ts) && raw.includes(" ")) {
    ts = Date.parse(raw.replace(" ", "T"));
  }
  if (!Number.isFinite(ts)) return 0;
  return ts > 0 ? ts : 0;
}

function formatLdapTimestamp(value) {
  const ts = parseLdapTimestamp(value);
  if (!ts) return "Never";
  return new Date(ts).toLocaleString();
}

function formatTimestampMs(ts) {
  if (!ts) return "Never";
  return new Date(ts).toLocaleString();
}

function latestActivityTs(user) {
  return Math.max(parseLdapTimestamp(user?.lastLogon), parseLdapTimestamp(user?.lastLogoff));
}

function activityToneClass(user) {
  const ts = latestActivityTs(user);
  if (!ts) return "none";

  const age = Date.now() - ts;
  if (age <= 3 * 24 * 60 * 60 * 1000) return "fresh";
  if (age <= 30 * 24 * 60 * 60 * 1000) return "normal";
  return "stale";
}

async function refreshAll() {
  if (refreshTimer !== null) {
    window.clearTimeout(refreshTimer);
    refreshTimer = null;
  }
  const seq = usersRequestSeq.value + 1;
  usersRequestSeq.value = seq;
  loading.value = true;
  error.value = "";
  try {
    let fromTs = parseInputDateTime(loginFrom.value);
    let toTs = parseInputDateTime(loginTo.value);
    if (fromTs && toTs && fromTs > toTs) {
      const tmp = fromTs;
      fromTs = toTs;
      toTs = tmp;
    }
    const [health, pagePayload, summary] = await Promise.all([
      apiLdapHealth(),
      apiListLdapUsersPage({
        view: "dashboard",
        page: currentPage.value,
        pageSize: pageSize.value,
        keyword: keyword.value,
        ouDns: selectedOuDns.value,
        ouScope: "subtree",
        groupCns: selectedGroups.value,
        loginFromMs: fromTs || undefined,
        loginToMs: toTs || undefined,
      }),
      apiLdapDashboardSummary({ recentWindowDays: 3 }),
    ]);
    if (seq !== usersRequestSeq.value) return;

    const items = Array.isArray(pagePayload?.items) ? pagePayload.items : [];
    status.value = health;
    users.value = items;
    totalUsers.value = Number(pagePayload?.total || 0);
    allUsersTotal.value = Number(summary?.total_users || 0);
    recent3DaysLoginCount.value = Number(summary?.recent_login_users || 0);
  } catch (e) {
    if (seq !== usersRequestSeq.value) return;
    error.value = e?.message || String(e);
  } finally {
    if (seq === usersRequestSeq.value) loading.value = false;
  }
}

async function ensureGroupsLoaded(force = false) {
  if (groupsLoaded.value && !force) return;
  loadingGroups.value = true;
  try {
    groups.value = await apiListLdapGroups({ includeMembers: false, includeDescription: false });
    groupsLoaded.value = true;
  } finally {
    loadingGroups.value = false;
  }
}

async function ensureOuTreeLoaded(force = false) {
  if (ouTreeLoaded.value && !force) return;
  loadingOuTree.value = true;
  try {
    const nextOuTree = await apiListLdapOuTree({ includeUsers: false });
    ouTree.value = nextOuTree;
    ouTreeLoaded.value = true;
    const allDns = new Set(collectOuDns(nextOuTree));
    const nextExpanded = new Set();
    for (const dn of expandedOuDns.value) {
      if (allDns.has(dn)) nextExpanded.add(dn);
    }
    for (const root of nextOuTree || []) {
      nextExpanded.add(normalizeDn(root.dn));
    }
    expandedOuDns.value = nextExpanded;
  } finally {
    loadingOuTree.value = false;
  }
}

async function toggleGroupDropdown() {
  const next = !groupDropdownOpen.value;
  groupDropdownOpen.value = next;
  if (!next) return;
  try {
    await ensureGroupsLoaded();
  } catch (e) {
    error.value = e?.message || String(e);
  }
}

async function toggleOuDropdown() {
  const next = !ouDropdownOpen.value;
  ouDropdownOpen.value = next;
  if (!next) return;
  try {
    await ensureOuTreeLoaded();
  } catch (e) {
    error.value = e?.message || String(e);
  }
}

function goPrevPage() {
  if (currentPage.value > 1) currentPage.value -= 1;
}

function goNextPage() {
  if (currentPage.value < totalPages.value) currentPage.value += 1;
}

function stopAutoScroll() {
  if (autoScrollTimer !== null) {
    window.clearInterval(autoScrollTimer);
    autoScrollTimer = null;
  }
}

function startAutoScroll() {
  stopAutoScroll();
  if (!autoScrollEnabled.value) return;

  autoScrollTimer = window.setInterval(() => {
    const el = tableWrapRef.value;
    if (!el) return;
    if (document.hidden) return;

    if (seamlessScrollActive.value) {
      const loopHeight = seamlessLoopHeightPx.value;
      if (loopHeight > el.clientHeight + 8) {
        const next = el.scrollTop + AUTO_SCROLL_STEP_PX;
        el.scrollTop = next >= loopHeight ? next - loopHeight : next;
        return;
      }
    }

    const maxTop = el.scrollHeight - el.clientHeight;
    if (maxTop <= 8) return;

    const next = el.scrollTop + AUTO_SCROLL_STEP_PX;
    if (next >= maxTop) {
      el.scrollTop = 0;
    } else {
      el.scrollTop = next;
    }
  }, AUTO_SCROLL_INTERVAL_MS);
}

function onClickOutside(event) {
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (!target.closest(".group-filter-inline")) {
    groupDropdownOpen.value = false;
  }
  if (!target.closest(".ou-filter-inline")) {
    ouDropdownOpen.value = false;
  }
}

function onTableWheel(event) {
  if (!autoScrollEnabled.value) return;
  event.preventDefault();
}

function scheduleRefresh(delayMs = 0) {
  if (refreshTimer !== null) {
    window.clearTimeout(refreshTimer);
    refreshTimer = null;
  }
  if (delayMs <= 0) {
    refreshAll();
    return;
  }
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null;
    refreshAll();
  }, delayMs);
}

onMounted(async () => {
  document.addEventListener("click", onClickOutside);
  await refreshAll();
  await recomputeSeamlessLoopHeight();
  startAutoScroll();
});

onUnmounted(() => {
  document.removeEventListener("click", onClickOutside);
  stopAutoScroll();
  if (refreshTimer !== null) {
    window.clearTimeout(refreshTimer);
    refreshTimer = null;
  }
});

watch([keyword, loginFrom, loginTo, selectedOuDns, selectedGroups, pageSize], () => {
  if (currentPage.value !== 1) {
    currentPage.value = 1;
    return;
  }
  const delay = keyword.value.trim() ? 220 : 0;
  scheduleRefresh(delay);
});

watch(currentPage, () => {
  scheduleRefresh(0);
});

watch(totalPages, (next) => {
  if (currentPage.value > next) currentPage.value = next;
});

watch(autoScrollEnabled, async (enabled) => {
  if (!enabled) {
    stopAutoScroll();
    return;
  }
  await recomputeSeamlessLoopHeight();
  startAutoScroll();
});

watch([paginatedUsers, currentPage, pageSize, seamlessScrollActive], async () => {
  await recomputeSeamlessLoopHeight();
  if (autoScrollEnabled.value) startAutoScroll();
});
</script>

<style scoped>
.dashboard-page {
  --bg-soft: #f4f8ff;
  --line-soft: #d8e4f5;
  --text-main: #0f172a;
  --text-sub: #64748b;
  --card-a: #eef6ff;
  --card-b: #f8fcff;
  --accent-blue: #2563eb;
  --accent-cyan: #0891b2;
  --accent-green: #059669;
  display: grid;
  gap: 16px;
  padding: 10px;
  border-radius: 16px;
  background: linear-gradient(180deg, #f7fbff 0%, var(--bg-soft) 100%);
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 12px;
}
.page-head h2 {
  margin: 0;
  line-height: 1.1;
}
.sub {
  margin: 6px 0 0;
  color: var(--text-sub);
  font-size: 13px;
}
.page-head-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.stats-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.stat-card {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  padding: 13px 14px;
  background: linear-gradient(155deg, var(--card-a) 0%, var(--card-b) 100%);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
}
.stat-card::after {
  content: "";
  position: absolute;
  right: 0;
  top: 0;
  width: 56px;
  height: 4px;
  border-radius: 0 0 0 8px;
  background: rgba(37, 99, 235, 0.35);
}
.stat-card.total::after {
  background: rgba(37, 99, 235, 0.45);
}
.stat-card.recent::after {
  background: rgba(8, 145, 178, 0.45);
}
.stat-card.status::after {
  background: rgba(5, 150, 105, 0.45);
}
.stat-label {
  font-size: 12px;
  color: var(--text-sub);
  margin-bottom: 4px;
}
.stat-value {
  font-size: 21px;
  font-weight: 700;
  color: var(--text-main);
}
.status-value {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 99px;
  background: #94a3b8;
}
.dot.ok {
  background: #22c55e;
}
.dot.bad {
  background: #ef4444;
}
.panel {
  border: 1px solid var(--line-soft);
  border-radius: 14px;
  padding: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
  min-width: 0;
  box-shadow: 0 6px 20px rgba(15, 23, 42, 0.05);
}
.filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.filters > * {
  min-width: 0;
}
.search-input {
  flex: 1 1 320px;
  min-width: 260px;
  height: 36px;
  box-sizing: border-box;
  border: 1px solid #c9d8ec;
  border-radius: 10px;
  padding: 0 12px;
  background: #fff;
}
.time-filter-label {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
}
.datetime-input {
  height: 36px;
  min-width: 180px;
  box-sizing: border-box;
  border: 1px solid #c9d8ec;
  border-radius: 10px;
  padding: 0 10px;
  background: #fff;
  color: #0f172a;
}
.select {
  height: 36px;
  min-width: 220px;
  border: 1px solid #d2d8e0;
  border-radius: 10px;
  padding: 0 10px;
  background: #fff;
  color: #0f172a;
}
.select.small {
  min-width: 82px;
  margin-left: 6px;
}
.btn {
  height: 36px;
  padding: 0 14px;
  border: 1px solid #d3dde8;
  border-radius: 10px;
  background: linear-gradient(180deg, #fbfdff 0%, #f3f8ff 100%);
  color: #0f172a;
  font-weight: 600;
}
.btn:hover {
  background: linear-gradient(180deg, #f2f7ff 0%, #e9f1ff 100%);
}
.btn:disabled {
  opacity: 0.6;
}
.ou-filter-inline,
.group-filter-inline {
  position: relative;
  flex: 0 1 250px;
}
.ou-trigger-btn {
  width: 100%;
  min-width: 180px;
  max-width: 280px;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.group-filter-inline > .btn {
  width: 100%;
  min-width: 150px;
}
.ou-dropdown-panel,
.group-dropdown-panel {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  width: min(420px, 82vw);
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  padding: 8px;
  display: grid;
  gap: 8px;
  z-index: 10;
}
.group-filter-inline .group-dropdown-panel {
  left: auto;
  right: 0;
  width: min(420px, calc(100vw - 56px));
}
.ou-search-input,
.group-search-input {
  width: 100%;
  height: 34px;
  box-sizing: border-box;
  border: 1px solid #cfd8e3;
  border-radius: 8px;
  padding: 0 10px;
}
.ou-all-btn {
  justify-content: flex-start;
}
.ou-all-btn.active {
  background: #e6f0ff;
  border-color: #bcd3f6;
}
.ou-tree-picker {
  max-height: 260px;
  overflow: auto;
  border: 1px solid #e6edf4;
  border-radius: 8px;
  padding: 6px;
  background: #fbfdff;
}
.ou-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 24px;
  margin: 1px 0;
}
.ou-row-btn {
  border: none;
  background: transparent;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 4px;
  border-radius: 6px;
  cursor: pointer;
  color: #0f172a;
  min-width: 0;
}
.ou-row-check {
  width: 14px;
  height: 14px;
  margin: 0 2px 0 0;
}
.ou-row-btn:hover {
  background: #f1f5f9;
}
.ou-row.active .ou-row-btn {
  background: #e6f0ff;
}
.ou-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 250px;
}
.ou-tag {
  border-radius: 999px;
  font-size: 11px;
  line-height: 1;
  padding: 2px 6px;
  border: 1px solid #dbe3ef;
  color: #334155;
  background: #eff6ff;
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
.ou-panel-actions,
.group-panel-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.ou-hit-summary {
  display: grid;
  gap: 6px;
}
.ou-hit-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ou-hit-chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid #dbe3ef;
  border-radius: 999px;
  padding: 2px 8px;
  background: #f8fbff;
  color: #334155;
  font-size: 12px;
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
.table-wrap {
  position: relative;
  max-height: 62vh;
  overflow: auto;
  scrollbar-gutter: stable both-edges;
  border: 1px solid #d9e5f3;
  border-radius: 12px;
  background: #fff;
}
.table-wrap.loading {
  pointer-events: none;
}
.table-wrap.autoscroll {
  overflow-y: hidden;
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.table-wrap.autoscroll::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}
.log-table {
  width: 100%;
  min-width: 1280px;
  border-collapse: separate;
  border-spacing: 0;
}
.log-table th,
.log-table td {
  border-bottom: 1px solid #edf2f7;
  padding: 10px 12px;
  text-align: left;
  vertical-align: top;
  font-size: 13px;
}
.log-table th {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #64748b;
  background: linear-gradient(180deg, #f8fbff 0%, #f2f8ff 100%);
  position: sticky;
  top: 0;
  z-index: 1;
  box-shadow: inset 0 -1px 0 #d9e5f4;
}
.log-table tbody tr {
  transition: background-color 140ms ease;
}
.log-table tbody tr.stripe-odd {
  background: #fcfdff;
}
.log-table tbody tr.stripe-even {
  background: #ffffff;
}
.log-table tbody tr:hover {
  background: #eef6ff;
}
.log-table tbody tr:last-child td {
  border-bottom: none;
}
.user-col {
  min-width: 130px;
}
.user-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border-radius: 999px;
  border: 1px solid #d4e4ff;
  background: linear-gradient(180deg, #f3f8ff 0%, #ebf4ff 100%);
  color: #1e3a8a;
  font-weight: 700;
  letter-spacing: 0.01em;
}
.time-cell.time-empty {
  color: #94a3b8;
}
.activity-chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid #dbe6f4;
  border-radius: 999px;
  padding: 2px 9px;
  background: #f8fafc;
  color: #334155;
  font-weight: 600;
}
.activity-chip.fresh {
  border-color: #a7f3d0;
  background: #ecfdf5;
  color: #065f46;
}
.activity-chip.normal {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
}
.activity-chip.stale {
  border-color: #fde68a;
  background: #fffbeb;
  color: #92400e;
}
.activity-chip.none {
  border-color: #e2e8f0;
  background: #f8fafc;
  color: #64748b;
}
.empty-row td {
  text-align: center;
  padding: 20px 12px;
}
.group-cell {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  max-width: 280px;
}
.group-chip {
  background: #edf4ff;
  color: #1e3a8a;
  border: 1px solid #cdddff;
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 12px;
  line-height: 1.4;
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
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}
.error {
  color: #b00020;
  background: #fde7ea;
  border: 1px solid #f5c2c7;
  padding: 10px;
  border-radius: 10px;
  white-space: pre-wrap;
}
.muted {
  color: #77818f;
}
.small-gap {
  padding: 8px;
}

@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .page-head {
    flex-direction: column;
    align-items: stretch;
  }
  .filters {
    flex-wrap: wrap;
    overflow-x: visible;
    align-items: stretch;
  }
  .search-input,
  .time-filter-label,
  .datetime-input,
  .select,
  .filters > .btn,
  .ou-filter-inline,
  .group-filter-inline {
    width: 100%;
    min-width: 0;
    flex: 1 1 auto;
  }
  .ou-trigger-btn {
    width: 100%;
    min-width: 0;
  }
  .ou-dropdown-panel,
  .group-dropdown-panel {
    width: 100%;
  }
  .group-filter-inline .group-dropdown-panel {
    left: 0;
    right: auto;
  }
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
