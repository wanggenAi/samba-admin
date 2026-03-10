// frontend/src/api/client.js

async function request(path, options = {}) {
    const res = await fetch(path, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });

    // FastAPI error (e.g. 500) try to read json/text
    const text = await res.text();
    let data;
    try {
        data = text ? JSON.parse(text) : null;
    } catch {
        data = text;
    }

    if (!res.ok) {
        // normalize error
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

export function apiListLdapUsers() {
    return request("/api/ldap/users");
}

export function apiListLdapGroups() {
    return request("/api/ldap/groups");
}

export function apiListLdapOuTree() {
    return request("/api/ldap/ou-tree");
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
