export type ApiError = {
  code: string;
  message: string;
  fields?: Record<string, unknown>;
};

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export async function ensureCsrf(): Promise<string> {
  const fromCookie = readCookie("csrftoken");
  if (fromCookie) return fromCookie;
  const res = await fetch("/api/v1/auth/csrf", { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch CSRF token");
  const data = (await res.json()) as { csrfToken: string };
  return data.csrfToken;
}

export function clearCsrf() {
  // Cookie is managed by Django; no client cache to clear.
}

export async function api<T>(
  path: string,
  options: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const headers = new Headers(options.headers || {});
  const method = (options.method || "GET").toUpperCase();
  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (method !== "GET" && method !== "HEAD") {
    const token = await ensureCsrf();
    headers.set("X-CSRFToken", token);
  }
  const res = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: "include",
    body: options.json !== undefined ? JSON.stringify(options.json) : options.body,
  });

  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = data as ApiError;
    throw Object.assign(new Error(err.message || res.statusText), {
      code: err.code || "error",
      fields: err.fields || {},
      status: res.status,
    });
  }
  return data as T;
}

export type Me = {
  id: string;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  totp_enabled: boolean;
  pending_2fa_setup: boolean;
  is_superuser: boolean;
  active_facility_id: string | null;
  roles: string[];
  screens: { id: string; code: string; module: string; name: string; route: string }[];
  memberships: {
    facility_id: string;
    facility_code: string;
    facility_name: string;
    role_code: string;
    role_name: string;
  }[];
};
