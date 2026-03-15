<template>
  <div class="sys-admin-page">
    <header class="page-head">
      <div>
        <h2>System Management</h2>
        <p class="muted">Manage local auth users, permissions, and roles.</p>
      </div>
      <button class="btn" type="button" :disabled="loading" @click="refreshAll">{{ loading ? "Refreshing..." : "Refresh" }}</button>
    </header>

    <section class="panel">
      <h3>Create User</h3>
      <div class="form-row">
        <div class="field-block">
          <input
            v-model.trim="newUser.username"
            placeholder="username"
            :class="{ invalid: showCreateUserErrors && !!createUserErrors.username }"
          />
          <p v-if="showCreateUserErrors && createUserErrors.username" class="field-error">{{ createUserErrors.username }}</p>
        </div>
        <div class="field-block">
          <input
            v-model="newUser.password"
            type="text"
            placeholder="password"
            :class="{ invalid: showCreateUserErrors && !!createUserErrors.password }"
          />
          <p v-if="showCreateUserErrors && createUserErrors.password" class="field-error">{{ createUserErrors.password }}</p>
        </div>
        <label class="inline">
          <input v-model="newUser.disabled" type="checkbox" />
          disabled
        </label>
      </div>
      <div class="role-checks" :class="{ 'invalid-wrap': showCreateUserErrors && !!createUserErrors.roles }">
        <label v-for="r in roles" :key="r.name" class="inline">
          <input
            type="checkbox"
            :checked="newUser.roles.includes(r.name)"
            @change="toggleNewUserRole(r.name, $event.target.checked)"
          />
          {{ r.name }}
        </label>
      </div>
      <p v-if="showCreateUserErrors && createUserErrors.roles" class="field-error">{{ createUserErrors.roles }}</p>
      <button
        class="btn primary"
        type="button"
        :disabled="savingUser"
        @click="createUser"
      >
        {{ savingUser ? "Saving..." : "Create User" }}
      </button>
    </section>

    <section class="panel">
      <h3>Users</h3>
      <div class="table-wrap" :class="{ loading: loading }">
        <table>
          <thead>
            <tr>
              <th>Username</th>
              <th>Roles</th>
              <th>Disabled</th>
              <th>Permissions</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.username">
              <td class="mono">{{ u.username }}</td>
              <td>{{ (u.roles || []).join(", ") || "-" }}</td>
              <td>{{ u.disabled ? "yes" : "no" }}</td>
              <td class="perm-cell">{{ (u.permissions || []).join(", ") || "-" }}</td>
              <td>
                <button class="btn" type="button" @click="startEditUser(u)">Edit</button>
                <button
                  class="btn danger"
                  type="button"
                  :disabled="u.username === authUserName"
                  @click="removeUser(u.username)"
                >
                  Delete
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <DataLoadingOverlay :show="loading" text="Loading users..." />
      </div>
    </section>

    <section class="panel">
      <h3>Permission Management</h3>
      <p class="section-help">System = built-in item provided by the app. System permissions are protected.</p>
      <div class="form-row">
        <div class="field-block">
          <input
            v-model.trim="newPermission.name"
            placeholder="permission name (e.g. reports.view)"
            :class="{ invalid: showCreatePermissionErrors && !!createPermissionErrors.name }"
          />
          <p v-if="showCreatePermissionErrors && createPermissionErrors.name" class="field-error">{{ createPermissionErrors.name }}</p>
        </div>
        <div class="field-block">
          <input v-model.trim="newPermission.description" placeholder="description" />
        </div>
      </div>
      <button class="btn primary" type="button" :disabled="savingPermission" @click="createPermission">
        {{ savingPermission ? "Saving..." : "Create Permission" }}
      </button>

      <div class="table-wrap mt-10" :class="{ loading: loading }">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Description</th>
              <th title="System means built-in and protected">System</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in permissions" :key="p.name">
              <td class="mono">{{ p.name }}</td>
              <td>{{ p.description || "-" }}</td>
              <td>{{ p.builtin ? "yes" : "no" }}</td>
              <td>
                <button class="btn" type="button" :disabled="p.builtin" @click="startEditPermission(p)">Edit</button>
                <button class="btn danger" type="button" :disabled="p.builtin" @click="removePermission(p.name)">Delete</button>
              </td>
            </tr>
          </tbody>
        </table>
        <DataLoadingOverlay :show="loading" text="Loading permissions..." />
      </div>
    </section>

    <section class="panel">
      <h3>Roles</h3>
      <p class="section-help">System = built-in role. System roles are protected from deletion.</p>
      <div class="form-row">
        <div class="field-block">
          <input
            v-model.trim="newRole.name"
            placeholder="role name"
            :class="{ invalid: showCreateRoleErrors && !!createRoleErrors.name }"
          />
          <p v-if="showCreateRoleErrors && createRoleErrors.name" class="field-error">{{ createRoleErrors.name }}</p>
        </div>
        <div class="field-block">
          <input v-model.trim="newRole.description" placeholder="description" />
        </div>
      </div>
      <div class="perm-grid" :class="{ 'invalid-wrap': showCreateRoleErrors && !!createRoleErrors.permissions }">
        <label v-for="p in permissions" :key="p.name" class="perm-item">
          <input
            type="checkbox"
            :checked="newRole.permissions.includes(p.name)"
            @change="toggleNewRolePerm(p.name, $event.target.checked)"
          />
          <span class="perm-name">{{ p.name }}</span>
          <span class="perm-desc">{{ p.description }}</span>
        </label>
      </div>
      <p v-if="showCreateRoleErrors && createRoleErrors.permissions" class="field-error">{{ createRoleErrors.permissions }}</p>
      <button
        class="btn primary"
        type="button"
        :disabled="savingRole"
        @click="createRole"
      >
        {{ savingRole ? "Saving..." : "Create Role" }}
      </button>

      <div class="table-wrap mt-10" :class="{ loading: loading }">
        <table>
          <thead>
            <tr>
              <th>Role</th>
              <th>Description</th>
              <th>Permissions</th>
              <th title="System means built-in and protected">System</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in roles" :key="r.name">
              <td class="mono">{{ r.name }}</td>
              <td>{{ r.description || "-" }}</td>
              <td class="perm-cell">{{ (r.permissions || []).join(", ") || "-" }}</td>
              <td>{{ r.builtin ? "yes" : "no" }}</td>
              <td>
                <button class="btn" type="button" :disabled="r.builtin && r.name === 'super_admin'" @click="startEditRole(r)">Edit</button>
                <button class="btn danger" type="button" :disabled="r.builtin" @click="removeRole(r.name)">Delete</button>
              </td>
            </tr>
          </tbody>
        </table>
        <DataLoadingOverlay :show="loading" text="Loading roles..." />
      </div>
    </section>

    <div v-if="editPermission.open" class="modal-mask" @click.self="closePermissionModal">
      <div class="modal">
        <h3>Edit Permission {{ editPermission.name }}</h3>
        <input
          v-model.trim="editPermission.description"
          placeholder="description"
          :class="{ invalid: showEditPermissionErrors && !!editPermissionErrors.description }"
        />
        <p v-if="showEditPermissionErrors && editPermissionErrors.description" class="field-error">
          {{ editPermissionErrors.description }}
        </p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closePermissionModal">Cancel</button>
          <button class="btn primary" type="button" @click="savePermissionEdit">Save</button>
        </div>
      </div>
    </div>

    <div v-if="editRole.open" class="modal-mask" @click.self="closeRoleModal">
      <div class="modal">
        <h3>Edit Role {{ editRole.name }}</h3>
        <input v-model.trim="editRole.description" placeholder="description" />
        <div class="perm-grid" :class="{ 'invalid-wrap': showEditRoleErrors && !!editRoleErrors.permissions }">
          <label v-for="p in permissions" :key="p.name" class="perm-item">
            <input
              type="checkbox"
              :checked="editRole.permissions.includes(p.name)"
              @change="toggleEditRolePerm(p.name, $event.target.checked)"
            />
            <span class="perm-name">{{ p.name }}</span>
          </label>
        </div>
        <p v-if="showEditRoleErrors && editRoleErrors.permissions" class="field-error">{{ editRoleErrors.permissions }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeRoleModal">Cancel</button>
          <button class="btn primary" type="button" @click="saveRoleEdit">Save</button>
        </div>
      </div>
    </div>

    <div v-if="editUser.open" class="modal-mask" @click.self="closeUserModal">
      <div class="modal">
        <h3>Edit User {{ editUser.username }}</h3>
        <input
          v-model="editUser.password"
          type="text"
          placeholder="new password (optional)"
          :class="{ invalid: showEditUserErrors && !!editUserErrors.password }"
        />
        <p v-if="showEditUserErrors && editUserErrors.password" class="field-error">{{ editUserErrors.password }}</p>
        <label class="inline">
          <input v-model="editUser.disabled" type="checkbox" />
          disabled
        </label>
        <div class="role-checks" :class="{ 'invalid-wrap': showEditUserErrors && !!editUserErrors.roles }">
          <label v-for="r in roles" :key="r.name" class="inline">
            <input
              type="checkbox"
              :checked="editUser.roles.includes(r.name)"
              @change="toggleEditUserRole(r.name, $event.target.checked)"
            />
            {{ r.name }}
          </label>
        </div>
        <p v-if="showEditUserErrors && editUserErrors.roles" class="field-error">{{ editUserErrors.roles }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeUserModal">Cancel</button>
          <button class="btn primary" type="button" @click="saveUserEdit">Save</button>
        </div>
      </div>
    </div>

    <div v-if="error || okMessage" class="global-toast-wrap">
      <p class="global-toast" :class="error ? 'error' : 'ok'">
        {{ error || okMessage }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import DataLoadingOverlay from "../../components/DataLoadingOverlay.vue";
import {
  apiCreateAdminPermission,
  apiCreateAdminRole,
  apiCreateAdminUser,
  apiDeleteAdminPermission,
  apiDeleteAdminRole,
  apiDeleteAdminUser,
  apiListAdminPermissions,
  apiListAdminRoles,
  apiListAdminUsers,
  apiUpdateAdminPermission,
  apiUpdateAdminRole,
  apiUpdateAdminUser,
} from "../../api/client";
import { useAuthStore } from "../../auth/store";

const auth = useAuthStore();
const authUserName = computed(() => auth.user()?.username || "");

const loading = ref(false);
const savingRole = ref(false);
const savingUser = ref(false);
const savingPermission = ref(false);
const error = ref("");
const okMessage = ref("");

const permissions = ref([]);
const roles = ref([]);
const users = ref([]);

const newPermission = reactive({ name: "", description: "" });
const newRole = reactive({ name: "", description: "", permissions: [] });
const newUser = reactive({ username: "", password: "", roles: [], disabled: false });

const editPermission = reactive({ open: false, name: "", description: "" });
const editRole = reactive({ open: false, name: "", description: "", permissions: [] });
const editUser = reactive({ open: false, username: "", password: "", roles: [], disabled: false });
const attempt = reactive({
  createUser: false,
  createPermission: false,
  createRole: false,
  editPermission: false,
  editRole: false,
  editUser: false,
});

const USERNAME_RE = /^[a-zA-Z0-9._-]{3,64}$/;
const PERMISSION_RE = /^[a-z0-9._-]{3,64}$/;
const MIN_PASSWORD_LENGTH = 6;

const createUserErrors = computed(() => {
  const out = { username: "", password: "", roles: "" };
  const username = newUser.username.trim();
  if (!username) out.username = "Username is required.";
  else if (!USERNAME_RE.test(username)) out.username = "Username: 3-64 chars, letters/numbers/._- only.";
  if (!newUser.password) out.password = "Password is required.";
  else if (newUser.password.length < MIN_PASSWORD_LENGTH) out.password = `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  if (!newUser.roles.length) out.roles = "Select at least one role.";
  return out;
});

const isCreateUserFormValid = computed(
  () => !createUserErrors.value.username && !createUserErrors.value.password && !createUserErrors.value.roles,
);
const showCreateUserErrors = computed(() => attempt.createUser);

const createPermissionErrors = computed(() => {
  const out = { name: "" };
  const name = newPermission.name.trim();
  if (!name) out.name = "Permission name is required.";
  else if (!PERMISSION_RE.test(name)) out.name = "Permission name: 3-64 chars, lowercase letters/numbers/._-.";
  return out;
});
const showCreatePermissionErrors = computed(() => attempt.createPermission);

const createRoleErrors = computed(() => {
  const out = { name: "", permissions: "" };
  const name = newRole.name.trim();
  if (!name) out.name = "Role name is required.";
  else if (!USERNAME_RE.test(name)) out.name = "Role name: 3-64 chars, letters/numbers/._- only.";
  if (!newRole.permissions.length) out.permissions = "Select at least one permission.";
  return out;
});
const isCreateRoleFormValid = computed(() => !createRoleErrors.value.name && !createRoleErrors.value.permissions);
const showCreateRoleErrors = computed(() => attempt.createRole);

const editPermissionErrors = computed(() => ({
  description: editPermission.description.trim() ? "" : "Description is required.",
}));
const showEditPermissionErrors = computed(() => attempt.editPermission);

const editRoleErrors = computed(() => ({
  permissions: editRole.permissions.length ? "" : "Select at least one permission.",
}));
const showEditRoleErrors = computed(() => attempt.editRole);

const editUserErrors = computed(() => {
  const out = { password: "", roles: "" };
  if (editUser.password && editUser.password.length < MIN_PASSWORD_LENGTH) {
    out.password = `New password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (!editUser.roles.length) out.roles = "Select at least one role.";
  return out;
});
const showEditUserErrors = computed(() => attempt.editUser);

const roleNameSet = computed(() => new Set((roles.value || []).map((r) => String(r?.name || "").trim()).filter(Boolean)));
const permissionNameSet = computed(() =>
  new Set((permissions.value || []).map((p) => String(p?.name || "").trim()).filter(Boolean)),
);

function filterKnownRoles(values) {
  const known = roleNameSet.value;
  return (values || []).filter((name) => known.has(String(name || "").trim()));
}

function filterKnownPermissions(values) {
  const known = permissionNameSet.value;
  return (values || []).filter((name) => known.has(String(name || "").trim()));
}

function reconcileSelections() {
  newUser.roles = filterKnownRoles(newUser.roles);
  editUser.roles = filterKnownRoles(editUser.roles);
  newRole.permissions = filterKnownPermissions(newRole.permissions);
  editRole.permissions = filterKnownPermissions(editRole.permissions);
}

function flashOk(msg) {
  okMessage.value = msg;
  setTimeout(() => {
    if (okMessage.value === msg) okMessage.value = "";
  }, 2200);
}

function setError(err, fallback) {
  error.value = err?.message || fallback;
}

function clearError() {
  error.value = "";
}

async function refreshAll() {
  loading.value = true;
  clearError();
  try {
    const [ps, rs, us] = await Promise.all([apiListAdminPermissions(), apiListAdminRoles(), apiListAdminUsers()]);
    permissions.value = ps || [];
    roles.value = rs || [];
    users.value = us || [];
    reconcileSelections();
  } catch (err) {
    setError(err, "Load failed");
  } finally {
    loading.value = false;
  }
}

function toggleNewRolePerm(name, checked) {
  const set = new Set(newRole.permissions);
  if (checked) set.add(name);
  else set.delete(name);
  newRole.permissions = Array.from(set);
}

function toggleEditRolePerm(name, checked) {
  const set = new Set(editRole.permissions);
  if (checked) set.add(name);
  else set.delete(name);
  editRole.permissions = Array.from(set);
}

function toggleNewUserRole(name, checked) {
  const set = new Set(newUser.roles);
  if (checked) set.add(name);
  else set.delete(name);
  newUser.roles = Array.from(set);
}

function toggleEditUserRole(name, checked) {
  const set = new Set(editUser.roles);
  if (checked) set.add(name);
  else set.delete(name);
  editUser.roles = Array.from(set);
}

async function createPermission() {
  attempt.createPermission = true;
  if (createPermissionErrors.value.name) {
    setError({ message: createPermissionErrors.value.name }, "Create permission failed");
    return;
  }
  savingPermission.value = true;
  clearError();
  try {
    await apiCreateAdminPermission({ name: newPermission.name, description: newPermission.description });
    newPermission.name = "";
    newPermission.description = "";
    attempt.createPermission = false;
    await refreshAll();
    flashOk("Permission created");
  } catch (err) {
    setError(err, "Create permission failed");
  } finally {
    savingPermission.value = false;
  }
}

function startEditPermission(permission) {
  if (permission.builtin) return;
  attempt.editPermission = false;
  editPermission.open = true;
  editPermission.name = permission.name;
  editPermission.description = permission.description || "";
}

function closePermissionModal() {
  attempt.editPermission = false;
  editPermission.open = false;
}

async function savePermissionEdit() {
  attempt.editPermission = true;
  if (editPermissionErrors.value.description) {
    setError({ message: editPermissionErrors.value.description }, "Update permission failed");
    return;
  }
  clearError();
  try {
    await apiUpdateAdminPermission(editPermission.name, { description: editPermission.description });
    closePermissionModal();
    await refreshAll();
    flashOk("Permission updated");
  } catch (err) {
    setError(err, "Update permission failed");
  }
}

async function removePermission(name) {
  if (!window.confirm(`Delete permission ${name}?`)) return;
  clearError();
  try {
    await apiDeleteAdminPermission(name);
    await refreshAll();
    flashOk("Permission deleted");
  } catch (err) {
    setError(err, "Delete permission failed");
  }
}

async function createRole() {
  attempt.createRole = true;
  if (createRoleErrors.value.name || createRoleErrors.value.permissions) {
    setError({ message: createRoleErrors.value.name || createRoleErrors.value.permissions }, "Create role failed");
    return;
  }
  savingRole.value = true;
  clearError();
  try {
    await apiCreateAdminRole({ ...newRole });
    newRole.name = "";
    newRole.description = "";
    newRole.permissions = [];
    attempt.createRole = false;
    await refreshAll();
    flashOk("Role created");
  } catch (err) {
    setError(err, "Create role failed");
  } finally {
    savingRole.value = false;
  }
}

function startEditRole(role) {
  attempt.editRole = false;
  editRole.open = true;
  editRole.name = role.name;
  editRole.description = role.description || "";
  editRole.permissions = [...(role.permissions || [])];
}

function closeRoleModal() {
  attempt.editRole = false;
  editRole.open = false;
}

async function saveRoleEdit() {
  attempt.editRole = true;
  if (editRoleErrors.value.permissions) {
    setError({ message: editRoleErrors.value.permissions }, "Update role failed");
    return;
  }
  clearError();
  try {
    await apiUpdateAdminRole(editRole.name, {
      description: editRole.description,
      permissions: editRole.permissions,
    });
    closeRoleModal();
    await refreshAll();
    flashOk("Role updated");
  } catch (err) {
    setError(err, "Update role failed");
  }
}

async function removeRole(name) {
  if (!window.confirm(`Delete role ${name}?`)) return;
  clearError();
  try {
    await apiDeleteAdminRole(name);
    await refreshAll();
    flashOk("Role deleted");
  } catch (err) {
    setError(err, "Delete role failed");
  }
}

async function createUser() {
  attempt.createUser = true;
  newUser.roles = filterKnownRoles(newUser.roles);
  if (createUserErrors.value.username || createUserErrors.value.password || createUserErrors.value.roles) {
    setError(
      { message: createUserErrors.value.username || createUserErrors.value.password || createUserErrors.value.roles },
      "Create user failed",
    );
    return;
  }
  savingUser.value = true;
  clearError();
  try {
    await apiCreateAdminUser({ ...newUser });
    newUser.username = "";
    newUser.password = "";
    newUser.roles = [];
    newUser.disabled = false;
    attempt.createUser = false;
    await refreshAll();
    flashOk("User created");
  } catch (err) {
    setError(err, "Create user failed");
  } finally {
    savingUser.value = false;
  }
}

function startEditUser(user) {
  attempt.editUser = false;
  editUser.open = true;
  editUser.username = user.username;
  editUser.password = "";
  editUser.roles = [...(user.roles || [])];
  editUser.disabled = !!user.disabled;
}

function closeUserModal() {
  attempt.editUser = false;
  editUser.open = false;
}

async function saveUserEdit() {
  attempt.editUser = true;
  editUser.roles = filterKnownRoles(editUser.roles);
  if (editUserErrors.value.roles) {
    setError({ message: editUserErrors.value.roles }, "Update user failed");
    return;
  }
  if (editUserErrors.value.password) {
    setError({ message: editUserErrors.value.password }, "Update user failed");
    return;
  }
  clearError();
  try {
    await apiUpdateAdminUser(editUser.username, {
      password: editUser.password || null,
      roles: editUser.roles,
      disabled: editUser.disabled,
    });
    closeUserModal();
    await refreshAll();
    flashOk("User updated");
  } catch (err) {
    setError(err, "Update user failed");
  }
}

async function removeUser(username) {
  if (!window.confirm(`Delete user ${username}?`)) return;
  clearError();
  try {
    await apiDeleteAdminUser(username);
    await refreshAll();
    flashOk("User deleted");
  } catch (err) {
    setError(err, "Delete user failed");
  }
}

onMounted(refreshAll);

watch(roles, () => {
  reconcileSelections();
});

watch(permissions, () => {
  reconcileSelections();
});
</script>

<style scoped>
.sys-admin-page {
  display: grid;
  gap: 14px;
}
.page-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}
.page-head h2 {
  margin: 0;
}
.muted {
  color: #6b7280;
  margin: 4px 0 0;
}
.panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px;
}
.panel h3 {
  margin: 0 0 10px;
}
.section-help {
  margin: -4px 0 10px;
  color: #6b7280;
  font-size: 12px;
}
.form-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
input[type="text"],
input[type="password"],
input:not([type]) {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 8px 10px;
  min-width: 220px;
}
.field-block {
  display: grid;
  gap: 4px;
}
.invalid {
  border-color: #dc2626 !important;
  box-shadow: 0 0 0 2px rgba(220, 38, 38, 0.12);
}
.invalid-wrap {
  border: 1px dashed #dc2626;
  border-radius: 8px;
  padding: 6px 8px;
}
.inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-right: 12px;
}
.role-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.perm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}
.perm-item {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 8px;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 8px;
  align-items: start;
}
.perm-name {
  font-weight: 700;
  font-size: 13px;
}
.perm-desc {
  grid-column: 2;
  color: #6b7280;
  font-size: 12px;
}
.table-wrap {
  position: relative;
  overflow: auto;
}
.table-wrap.loading {
  pointer-events: none;
}
.mt-10 {
  margin-top: 10px;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  border-bottom: 1px solid #eef2f7;
  text-align: left;
  vertical-align: top;
  padding: 8px;
  font-size: 13px;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.perm-cell {
  max-width: 380px;
  color: #374151;
  word-break: break-word;
}
.btn {
  border: 1px solid #d1d5db;
  background: #fff;
  border-radius: 8px;
  padding: 6px 10px;
  cursor: pointer;
  margin-right: 6px;
}
.btn.primary {
  background: #1d4ed8;
  border-color: #1d4ed8;
  color: #fff;
}
.btn.danger {
  background: #dc2626;
  border-color: #dc2626;
  color: #fff;
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.ok {
  color: #065f46;
  background: #d1fae5;
  border: 1px solid #a7f3d0;
  border-radius: 8px;
  padding: 8px 10px;
}
.error {
  color: #991b1b;
  background: #fee2e2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 8px 10px;
}
.field-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: #6b7280;
}
.field-error {
  margin: 0;
  font-size: 12px;
  color: #b91c1c;
}
.global-toast-wrap {
  position: fixed;
  top: 76px;
  right: 16px;
  z-index: 1200;
  width: min(460px, calc(100vw - 32px));
  pointer-events: none;
}
.global-toast {
  margin: 0;
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.18);
}
.modal-mask {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(17, 24, 39, 0.45);
  padding: 18px;
}
.modal {
  width: min(820px, 96vw);
  max-height: 90vh;
  overflow: auto;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  padding: 14px;
}
.modal h3 {
  margin-top: 0;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}
</style>
