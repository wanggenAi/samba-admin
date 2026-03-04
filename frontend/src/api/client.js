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
        const message =
            (data && data.detail) ||
            (typeof data === "string" ? data : JSON.stringify(data)) ||
            `HTTP ${res.status}`;
        throw new Error(message);
    }

    return data;
}

export function apiGetStatus() {
    return request("/api/system/status");
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