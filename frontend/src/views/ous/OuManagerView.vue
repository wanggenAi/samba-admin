<template>
  <div class="ou-page">
    <header class="page-head">
      <div>
        <h2>OU Manager</h2>
        <p class="sub">Manage organizational units in a dedicated workspace.</p>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="actionMessage" class="ok">{{ actionMessage }}</p>

    <section class="panel">
      <div class="panel-head">
        <div class="head-left">
          <h3>OU Tree</h3>
          <div v-if="selectedOuDn" class="active-filter">
            <span class="muted">Selected:</span>
            <code>{{ selectedOuPath || selectedOuDn }}</code>
          </div>
        </div>
        <div class="panel-actions tree-tools">
          <button class="btn" :disabled="loadingOuTree || ouOpLoading" @click="onRefreshTree">
            {{ loadingOuTree ? "Loading" : "Refresh" }}
          </button>
          <button class="btn" :disabled="loadingOuTree || !ouTree.length" @click="onExpandAllOu">+All</button>
          <button class="btn" :disabled="loadingOuTree || !ouTree.length" @click="onCollapseAllOu">-All</button>
          <button v-if="canRenameOu" class="btn" :disabled="loadingOuTree || ouOpLoading || !selectedOuDn" @click="openRenameModal">Edit OU</button>
          <button v-if="canDeleteOu" class="btn danger" :disabled="loadingOuTree || ouOpLoading || !selectedOuDn" @click="onDeleteOu">Del OU</button>
        </div>
      </div>

      <input
        v-model.trim="ouKeyword"
        type="text"
        class="search-input"
        placeholder="Search OU / user / DN"
      />

      <div v-if="canCreateOu" class="create-ou-box mt">
        <div class="create-ou-title">Create OU</div>
        <div class="create-ou-hint compact">
          Select parent in tree, then input one OU name (e.g. <code>63/24</code> or <code>ms</code>).
        </div>
        <details class="create-ou-help">
          <summary>Usage details</summary>
          <div class="create-ou-hint">Path separator: <code>&gt;</code> (example: <code>Students &gt; ms &gt; 63/24</code>).</div>
          <div class="create-ou-hint">Shorthand in user create/edit: <code>ms-63/24</code> = <code>Students &gt; ms &gt; 63/24</code>.</div>
          <div class="create-ou-hint">Do not use <code>/</code> or <code>;</code> as level separators. <code>/</code> can be part of OU name.</div>
        </details>
        <div class="create-ou-row">
          <input
            v-model.trim="newOuName"
            type="text"
            class="search-input"
            placeholder="New OU name"
            @keydown.enter.prevent="onCreateOu"
          />
          <button class="btn" :disabled="ouOpLoading || !newOuName.trim()" @click="onCreateOu">
            {{ ouOpLoading ? "Creating..." : "Create OU" }}
          </button>
        </div>
        <div class="muted">
          Parent: <code>{{ selectedOuDn ? (selectedOuPath || selectedOuDn) : "base DN" }}</code>
        </div>
      </div>

      <div class="tree-body-host mt" :class="{ loading: loadingOuTree }">
        <div v-if="!ouTreeLines.length" class="muted mt">No OU nodes found under current base DN.</div>
        <div v-else class="ou-tree-wrap mt">
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
        <DataLoadingOverlay :show="loadingOuTree" text="Loading OU tree..." />
      </div>
    </section>

    <div v-if="renameModalOpen" class="modal-mask" @click.self="closeRenameModal">
      <section class="modal-card" role="dialog" aria-modal="true" aria-label="Rename OU">
        <header class="modal-head">
          <h4>Rename OU</h4>
          <button class="btn icon-btn" type="button" @click="closeRenameModal">✕</button>
        </header>

        <div class="modal-body">
          <div class="field">
            <label>Current OU</label>
            <code>{{ renameCurrentName }}</code>
          </div>
          <div class="field">
            <label>New OU name</label>
            <input
              v-model.trim="renameNextName"
              class="search-input"
              type="text"
              placeholder="Input new OU name"
              @keydown.enter.prevent="submitRenameOu"
            />
          </div>

          <div class="notice">
            <div class="notice-title">Business Notes</div>
            <div class="notice-line">Renaming updates this OU and all descendant DNs automatically.</div>
            <div class="notice-line">Parent OU is unchanged. This is rename only, not move.</div>
            <div class="notice-line">Rename fails if another sibling OU already has the same target name.</div>
          </div>
        </div>

        <footer class="modal-actions">
          <button class="btn" type="button" @click="closeRenameModal">Cancel</button>
          <button
            class="btn primary"
            type="button"
            :disabled="ouOpLoading || !renameNextName.trim() || renameNextName.trim() === renameCurrentName"
            @click="submitRenameOu"
          >
            {{ ouOpLoading ? "Saving..." : "Save Rename" }}
          </button>
        </footer>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import DataLoadingOverlay from "../../components/DataLoadingOverlay.vue";
import { apiCreateLdapOu, apiDeleteLdapOu, apiListLdapOuTree, apiRenameLdapOu } from "../../api/client";
import { useAuthStore } from "../../auth/store";

const auth = useAuthStore();
const canCreateOu = computed(() => auth.hasPermission("ous.create"));
const canRenameOu = computed(() => auth.hasPermission("ous.rename"));
const canDeleteOu = computed(() => auth.hasPermission("ous.delete"));

const ouTree = ref([]);
const loadingOuTree = ref(false);
const ouOpLoading = ref(false);
const error = ref("");
const actionMessage = ref("");
const ouKeyword = ref("");
const newOuName = ref("");
const selectedOuDn = ref("");
const selectedOuPath = ref("");
const expandedOuDns = ref(new Set());
const renameModalOpen = ref(false);
const renameSourceDn = ref("");
const renameCurrentName = ref("");
const renameNextName = ref("");

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

function ouNameFromDn(dn) {
  const first = String(dn || "").split(",", 1)[0].trim();
  if (!first.toUpperCase().startsWith("OU=")) return String(dn || "");
  return first.slice(3);
}

function clearOuFilter() {
  selectedOuDn.value = "";
  selectedOuPath.value = "";
}

function onExpandAllOu() {
  expandedOuDns.value = new Set(collectOuDns(ouTree.value));
}

function onCollapseAllOu() {
  expandedOuDns.value = new Set();
}

function onTreeLineClick(line) {
  if (!line || line.type !== "ou") return;
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

async function refreshOuTree() {
  loadingOuTree.value = true;
  error.value = "";
  try {
    const nextTree = await apiListLdapOuTree({ includeUsers: true, userView: "tree" });
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

async function onRefreshTree() {
  ouKeyword.value = "";
  clearOuFilter();
  actionMessage.value = "";
  await refreshOuTree();
}

async function onCreateOu() {
  if (!canCreateOu.value) return;
  const name = String(newOuName.value || "").trim();
  if (!name) return;

  ouOpLoading.value = true;
  error.value = "";
  actionMessage.value = "";
  try {
    const parent_dn = selectedOuDn.value || null;
    const res = await apiCreateLdapOu({ name, parent_dn });
    actionMessage.value = res.created ? `Created OU: ${name}` : `OU already exists: ${name}`;
    newOuName.value = "";
    await refreshOuTree();
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    ouOpLoading.value = false;
  }
}

function openRenameModal() {
  if (!canRenameOu.value) return;
  const dn = selectedOuDn.value;
  if (!dn) return;
  const currentName = ouNameFromDn(dn);
  renameSourceDn.value = dn;
  renameCurrentName.value = currentName;
  renameNextName.value = currentName;
  renameModalOpen.value = true;
}

function closeRenameModal() {
  if (ouOpLoading.value) return;
  renameModalOpen.value = false;
  renameSourceDn.value = "";
  renameCurrentName.value = "";
  renameNextName.value = "";
}

async function submitRenameOu() {
  if (!canRenameOu.value) return;
  const dn = renameSourceDn.value;
  const currentName = renameCurrentName.value;
  const nextName = String(renameNextName.value || "").trim();
  if (!dn || !nextName || nextName === currentName) return;

  ouOpLoading.value = true;
  error.value = "";
  actionMessage.value = "";
  try {
    await apiRenameLdapOu(dn, nextName);
    actionMessage.value = `Renamed OU \"${currentName}\" to \"${nextName}\". Child nodes were updated automatically.`;
    closeRenameModal();
    clearOuFilter();
    await refreshOuTree();
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    ouOpLoading.value = false;
  }
}

async function onDeleteOu() {
  if (!canDeleteOu.value) return;
  const dn = selectedOuDn.value;
  if (!dn) return;
  const ouName = ouNameFromDn(dn);

  const ok = window.confirm(`Delete OU "${ouName}"?\nOnly empty OUs can be deleted without recursion.`);
  if (!ok) return;

  ouOpLoading.value = true;
  error.value = "";
  actionMessage.value = "";
  try {
    const res = await apiDeleteLdapOu(dn, false);
    actionMessage.value = `Deleted OU "${ouName}" (${res.deleted_entries} entries).`;
    clearOuFilter();
    await refreshOuTree();
    return;
  } catch (e) {
    if (e?.status === 409) {
      const confirmRecursive = window.confirm(
        `OU "${ouName}" is not empty.\nDelete this OU and all descendants (users/sub-OUs)? This cannot be undone.`
      );
      if (!confirmRecursive) {
        ouOpLoading.value = false;
        return;
      }
      try {
        const res = await apiDeleteLdapOu(dn, true);
        actionMessage.value = `Recursively deleted OU "${ouName}" (${res.deleted_entries} entries).`;
        clearOuFilter();
        await refreshOuTree();
        return;
      } catch (e2) {
        error.value = e2?.message || String(e2);
        return;
      }
    }
    error.value = e?.message || String(e);
  } finally {
    ouOpLoading.value = false;
  }
}

onMounted(async () => {
  await refreshOuTree();
});
</script>

<style scoped>
.ou-page {
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
.panel {
  border: 1px solid #dde5ef;
  border-radius: 14px;
  padding: 14px;
  background: #ffffff;
  min-width: 0;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.head-left {
  display: grid;
  gap: 6px;
}
.panel-head h3 {
  margin: 0;
  font-size: 20px;
}
.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
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
.btn.danger {
  background: #fff1f2;
  border-color: #fecdd3;
  color: #9f1239;
}
.btn.primary {
  background: #0f172a;
  border-color: #0f172a;
  color: #fff;
}
.icon-btn {
  width: 34px;
  min-width: 34px;
  padding: 0;
}
.search-input {
  width: 100%;
  height: 36px;
  box-sizing: border-box;
  border: 1px solid #cfd8e3;
  border-radius: 10px;
  padding: 0 12px;
  background: #fff;
}
.mt {
  margin-top: 10px;
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
.create-ou-box {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 8px;
  display: grid;
  gap: 6px;
  background: #f8fafc;
}
.create-ou-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}
.create-ou-hint {
  color: #64748b;
  font-size: 13px;
  line-height: 1.35;
}
.create-ou-hint.compact {
  margin-bottom: 2px;
}
.create-ou-help {
  color: #64748b;
  font-size: 13px;
}
.create-ou-help summary {
  cursor: pointer;
  user-select: none;
}
.create-ou-help[open] {
  display: grid;
  gap: 4px;
}
.create-ou-row {
  display: flex;
  gap: 8px;
}
.create-ou-row .search-input {
  flex: 1;
}
.tree-body-host {
  position: relative;
  min-height: 120px;
}
.tree-body-host.loading {
  pointer-events: none;
}
.ou-tree-wrap {
  border: 1px solid #e6edf4;
  border-radius: 12px;
  padding: 10px;
  background: #fbfdff;
  display: grid;
  gap: 6px;
  max-height: 68vh;
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
.main-text {
  color: #0f172a;
  font-size: 14px;
  line-height: 1.1;
  font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif;
  font-weight: 600;
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
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  display: grid;
  place-items: center;
  z-index: 1200;
}
.modal-card {
  width: min(640px, calc(100vw - 32px));
  border: 1px solid #dbe3ef;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.25);
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid #eef2f7;
}
.modal-head h4 {
  margin: 0;
  font-size: 20px;
}
.modal-body {
  display: grid;
  gap: 10px;
  padding: 12px 14px;
}
.field {
  display: grid;
  gap: 6px;
}
.field label {
  font-size: 13px;
  color: #475569;
}
.notice {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px;
  background: #f8fafc;
  display: grid;
  gap: 4px;
}
.notice-title {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}
.notice-line {
  font-size: 13px;
  color: #475569;
  line-height: 1.35;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 14px;
  border-top: 1px solid #eef2f7;
}

@media (max-width: 1200px) {
  .panel-head {
    flex-direction: column;
    align-items: stretch;
  }
  .create-ou-row {
    flex-direction: column;
  }
}
</style>
