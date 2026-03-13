const ALLOWED_USER_VIEWS = new Set(["full", "list", "dashboard", "tree"]);

let authTokenGetter = null;

export function setAuthTokenGetter(getter) {
  authTokenGetter = typeof getter === "function" ? getter : null;
}

function getAuthToken() {
  try {
    return authTokenGetter ? authTokenGetter() : "";
  } catch {
    return "";
  }
}

async function request(path, options = {}) {
  const isFormDataBody = typeof FormData !== "undefined" && options.body instanceof FormData;
  const token = getAuthToken();
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};
  const headers = isFormDataBody
    ? { ...authHeaders, ...(options.headers || {}) }
    : { "Content-Type": "application/json", ...authHeaders, ...(options.headers || {}) };

  const res = await fetch(path, {
    headers,
    ...options,
  });

  const contentType = (res.headers.get("content-type") || "").toLowerCase();
  const isJson = contentType.includes("application/json");

  let data = null;
  if (isJson) {
    try {
      data = await res.json();
    } catch {
      data = null;
    }
  } else {
    data = await res.text();
  }

  if (!res.ok) {
    const detail = data && data.detail;
    const message =
      (typeof detail === "string" && detail.trim() ? detail : null) ||
      (detail && typeof detail === "object" ? JSON.stringify(detail) : null) ||
      (typeof data === "string" && data.trim() ? data : null) ||
      (data && typeof data === "object" ? JSON.stringify(data) : null) ||
      `HTTP ${res.status}`;
    const err = new Error(message);
    err.status = res.status;
    err.detail = detail;
    err.data = data;
    throw err;
  }

  return data;
}

export function apiLogin(payload) {
  return request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function apiMe() {
  return request("/api/auth/me");
}

export function apiChangePassword(payload) {
  return request("/api/auth/change-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function apiListAdminPermissions() {
  return request("/api/admin/permissions");
}

export function apiCreateAdminPermission(payload) {
  return request("/api/admin/permissions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function apiUpdateAdminPermission(name, payload) {
  return request(`/api/admin/permissions/${encodeURIComponent(name)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function apiDeleteAdminPermission(name) {
  return request(`/api/admin/permissions/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}

export function apiListAdminRoles() {
  return request("/api/admin/roles");
}

export function apiCreateAdminRole(payload) {
  return request("/api/admin/roles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function apiUpdateAdminRole(name, payload) {
  return request(`/api/admin/roles/${encodeURIComponent(name)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function apiDeleteAdminRole(name) {
  return request(`/api/admin/roles/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}

export function apiListAdminUsers() {
  return request("/api/admin/users");
}

export function apiCreateAdminUser(payload) {
  return request("/api/admin/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function apiUpdateAdminUser(username, payload) {
  return request(`/api/admin/users/${encodeURIComponent(username)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function apiDeleteAdminUser(username) {
  return request(`/api/admin/users/${encodeURIComponent(username)}`, {
    method: "DELETE",
  });
}

export function apiGetStatus() {
  return request("/api/system/status");
}

export function apiLdapHealth() {
  return request("/api/ldap/health");
}

export function apiValidateConfig(payload) {
  return request("/api/config/validate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function apiApplyConfig(payload) {
  return request("/api/config/apply", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function apiListVersions() {
  return request("/api/versions");
}

export function apiRollbackVersion(vid) {
  return request(`/api/versions/${encodeURIComponent(vid)}/rollback`, {
    method: "POST",
  });
}

export function apiListLdapUsers(options = {}) {
  const safe = String(options?.view || "full").trim().toLowerCase();
  const view = ALLOWED_USER_VIEWS.has(safe) ? safe : "full";
  const path = view === "full" ? "/api/ldap/users" : `/api/ldap/users?view=${encodeURIComponent(view)}`;
  return request(path);
}

export function apiListLdapGroups(options = {}) {
  const includeMembers = options?.includeMembers !== false;
  const includeDescription = options?.includeDescription === true;
  const params = new URLSearchParams();
  if (!includeMembers) params.set("include_members", "false");
  if (includeDescription) params.set("include_description", "true");
  const query = params.toString();
  const path = query ? `/api/ldap/groups?${query}` : "/api/ldap/groups";
  return request(path);
}

export function apiListLdapOuTree(options = {}) {
  const includeUsers = options?.includeUsers !== false;
  const rawView = String(options?.userView || "full").trim().toLowerCase();
  const userView = ALLOWED_USER_VIEWS.has(rawView) ? rawView : "full";
  const params = new URLSearchParams();
  if (!includeUsers) params.set("include_users", "false");
  if (includeUsers && userView && userView !== "full") params.set("user_view", userView);
  const query = params.toString();
  const path = query ? `/api/ldap/ou-tree?${query}` : "/api/ldap/ou-tree";
  return request(path);
}

export function apiCreateLdapOu(payload) {
  return request("/api/ldap/ou", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function apiDeleteLdapOu(dn, recursive = false) {
  return request(`/api/ldap/ou?dn=${encodeURIComponent(dn)}&recursive=${recursive ? "true" : "false"}`, {
    method: "DELETE",
  });
}

export function apiRenameLdapOu(dn, new_name) {
  return request("/api/ldap/ou", {
    method: "PATCH",
    body: JSON.stringify({ dn, new_name }),
  });
}

export function apiAddUser(payload) {
  return request("/api/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function apiDeleteUser(username) {
  return request(`/api/users/${encodeURIComponent(username)}`, {
    method: "DELETE",
  });
}

export function apiImportUsers(files, { defaultGroupCn = "Students", passwordLength = 12 } = {}) {
  const form = new FormData();
  for (const file of files || []) {
    form.append("files", file);
  }
  if (defaultGroupCn !== null && defaultGroupCn !== undefined) {
    form.append("default_group_cn", String(defaultGroupCn));
  }
  form.append("password_length", String(passwordLength));

  return request("/api/users/import", {
    method: "POST",
    body: form,
  });
}

export async function apiExportUsers({ keyword = "", ouDn = "", groupCns = [] } = {}) {
  const params = new URLSearchParams();
  const kw = String(keyword || "").trim();
  if (kw) params.set("keyword", kw);

  const ou = String(ouDn || "").trim();
  if (ou) params.set("ou_dn", ou);

  for (const groupCn of groupCns || []) {
    const cn = String(groupCn || "").trim();
    if (cn) params.append("group_cn", cn);
  }

  const query = params.toString();
  const path = query ? `/api/users/export?${query}` : "/api/users/export";
  const token = getAuthToken();
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(path, { method: "GET", headers });
  if (!res.ok) {
    const text = await res.text();
    let data;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }
    const detail = data && data.detail;
    const message =
      (typeof detail === "string" && detail.trim() ? detail : null) ||
      (detail && typeof detail === "object" ? JSON.stringify(detail) : null) ||
      (typeof data === "string" && data.trim() ? data : null) ||
      (data && typeof data === "object" ? JSON.stringify(data) : null) ||
      `HTTP ${res.status}`;
    const err = new Error(message);
    err.status = res.status;
    err.detail = detail;
    err.data = data;
    throw err;
  }

  const contentDisposition = res.headers.get("content-disposition") || "";
  const match = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
  const filename = match?.[1] || "users-export.csv";
  const blob = await res.blob();
  return { filename, blob };
}
