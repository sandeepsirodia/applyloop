// Thin client for applyloop's existing JSON API (served by applyloop/ui.py). Every call attaches the
// session token as X-Token; a 403 means the token is missing or wrong, so we drop it and force a re-login.

export interface Settings {
  roles: string[];
  adjacent_accepted: string[];
  adjacent_suggested?: { family: string; median_cover: number; open: number; now: number }[];
  resumes: Record<string, { file: string; json: string; reviewed: boolean; findings: Finding[]; added: number }>;
  default_resume: string | null;
  level: string | null;
  remote: boolean;
  remote_from: string | null;
  location: string | null;
  auto_approve: boolean;
  fit_threshold: number;
  fit_floor: number;
  allow_drafted: boolean;
  daily_cap: number;
  daily_target: number;
  cooldown_days: number;
  blocklist: string[];
  kill_switch: boolean;
  dry_run: boolean;
  state: "paused" | "running";
}

export interface Finding { kind: string; message: string; evidence?: string }

export interface Answer { question: string; value: unknown; source: string; kind: string }

export interface Approval {
  job_id: string; company: string; title: string; fit: number; resume_variant: string;
  apply_url: string; screenshot_url: string | null; auto: string[]; answers: Answer[] | null;
}

export interface Question {
  id: number; question: string; options: string[] | null; reason: string;
  job?: { company?: string; title?: string };
}

export interface RecentJob {
  job_id: string; company: string; title: string; stage: string; reason: string | null;
  fit: number | null; updated_at: number;
}

export interface SiteBudget {
  used: Record<string, number>; limits: Record<string, number | null>;
  paused: { until: number | null; reason: string; needs_human: boolean } | null;
  breaker: { state: string; until: number } | null;
  next_allowed: number | null;
}

export interface Budgets { all_paused: { until: number | null; reason: string } | null; sites: Record<string, SiteBudget> }

export interface Outcomes { applications: number; report: string | null; how: string }

export interface LogEvent { ts: number; level: string; message: string }

export interface AppState {
  settings: Settings;
  counts: Record<string, number>;
  submitted_today: number;
  approvals: Approval[];
  waiting: { job_id: string; company: string; title: string; reason: string }[];
  recent: RecentJob[];
  questions: Question[];
  budgets: Budgets;
  events: LogEvent[];
  outcomes: Outcomes;
}

const TOKEN_KEY = "applyloop.token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(path, {
    ...init,
    headers: { ...(init?.headers || {}), ...(token ? { "X-Token": token } : {}) },
  });
  if (res.status === 403) {
    clearToken();
    throw new ApiError(403, "session expired: please log in again");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body.error || res.statusText);
  return body as T;
}

export const api = {
  login: (password: string) =>
    fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) })
      .then(async (r) => {
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new ApiError(r.status, body.error || "login failed");
        return body.token as string;
      }),
  state: () => request<AppState>("/api/state"),
  control: (action: string) => request("/api/control", { method: "POST", body: JSON.stringify({ action }) }),
  settings: (patch: Partial<Settings>) => request("/api/settings", { method: "POST", body: JSON.stringify(patch) }),
  addRole: (role: string) => request("/api/roles", { method: "POST", body: JSON.stringify({ add: role }) }),
  removeRole: (role: string) => request("/api/roles", { method: "POST", body: JSON.stringify({ remove: role }) }),
  approve: (job_id: string) => request("/api/approve", { method: "POST", body: JSON.stringify({ job_id }) }),
  reject: (job_id: string) => request("/api/reject", { method: "POST", body: JSON.stringify({ job_id }) }),
  answer: (id: number, value: string, when?: Record<string, string>) =>
    request("/api/answer", { method: "POST", body: JSON.stringify({ id, value, when }) }),
  budget: (site: string, action: "pause" | "resume") => request("/api/budget", { method: "POST", body: JSON.stringify({ site, action }) }),
  uploadResume: (label: string, filename: string, data: string) =>
    request<{ ok: boolean; label: string; findings: Finding[] }>("/api/resume", { method: "POST", body: JSON.stringify({ label, filename, data }) }),
  markReviewed: (label: string) => request("/api/resume/reviewed", { method: "POST", body: JSON.stringify({ label }) }),
};

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
