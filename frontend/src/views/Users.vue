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
        </label>
        <label>
          Password
          <input v-model="form.password" type="password" placeholder="Test@123456" />
        </label>
        <label>
          Student ID
          <input v-model.trim="form.student_id" type="text" placeholder="2026001" />
        </label>
        <label>
          Russian Name
          <input v-model.trim="form.russian_name" type="text" placeholder="Иван Иванов" />
        </label>
        <label>
          Pinyin Name
          <input v-model.trim="form.pinyin_name" type="text" placeholder="Zhang San" />
        </label>
        <label>
          Paid Flag (optional)
          <input v-model.trim="form.paid_flag" type="text" placeholder="$" maxlength="1" />
        </label>
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
        <table>
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
              <td>{{ u.sAMAccountName || "-" }}</td>
              <td>{{ u.displayName || "-" }}</td>
              <td>{{ u.userPrincipalName || "-" }}</td>
              <td class="dn">{{ u.dn }}</td>
            </tr>
            <tr v-if="!filteredUsers.length">
              <td colspan="4" class="muted">No users found.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pager" v-if="filteredUsers.length">
        <div class="pager-left muted">
          Total {{ filteredUsers.length }} users
        </div>
        <div class="pager-right">
          <label>
            Page size
            <select v-model.number="pageSize">
              <option :value="10">10</option>
              <option :value="20">20</option>
              <option :value="50">50</option>
            </select>
          </label>

          <button class="btn" :disabled="currentPage <= 1" @click="goPrevPage">Prev</button>
          <span class="muted">Page {{ currentPage }} / {{ totalPages }}</span>
          <button class="btn" :disabled="currentPage >= totalPages" @click="goNextPage">Next</button>
        </div>
      </div>

      <p class="muted">Delete feature will be added next.</p>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { apiAddUser, apiListLdapGroups, apiListLdapUsers } from "../api/client";

const users = ref([]);
const groups = ref([]);
const loadingUsers = ref(false);
const loadingGroups = ref(false);
const submitting = ref(false);
const error = ref("");
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

async function submit() {
  submitting.value = true;
  error.value = "";
  submitMessage.value = "";

  try {
    const payload = {
      ...form.value,
      paid_flag: form.value.paid_flag || null,
      groups: selectedGroups.value,
    };

    const res = await apiAddUser(payload);
    submitMessage.value = `Success: ${res.username} (${res.created ? "created" : "updated"}).`;
    await refreshUsers();
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  document.addEventListener("click", onClickOutside);
  await Promise.all([refreshUsers(), refreshGroups()]);
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
.table-wrap { overflow: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { border-bottom: 1px solid #eee; padding: 8px; text-align: left; vertical-align: top; }
.dn { max-width: 400px; word-break: break-all; }
.pager {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.pager-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
select {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 6px 8px;
  margin-left: 4px;
}
.error {
  color: #b00020;
  background: #fde7ea;
  border: 1px solid #f5c2c7;
  padding: 8px;
  border-radius: 8px;
  white-space: pre-wrap;
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
}
</style>
