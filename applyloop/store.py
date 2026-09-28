"""All of applyloop's state in one SQLite file, so the whole pipeline can stop and resume at any point."""
import json
import os
import sqlite3
import threading
import time

HOME = os.path.join(os.path.expanduser("~"), ".applyloop")

DEFAULTS = {
    "roles": [], "adjacent_accepted": [], "resumes": {}, "default_resume": None, "profile": {},
    "level": None, "remote": False, "location": None,
    "auto_approve": False, "fit_threshold": 0.75, "fit_floor": 0.55, "allow_drafted": False,
    "daily_cap": 15, "daily_target": 15, "cooldown_days": 90, "blocklist": [],
    "kill_switch": False, "dry_run": True, "state": "paused",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS pipeline (job_id TEXT PRIMARY KEY, company TEXT, title TEXT, apply_url TEXT, ats TEXT,
  location TEXT, description_text TEXT, fit REAL, parts TEXT, resume_variant TEXT, stage TEXT, reason TEXT, fields TEXT,
  answers TEXT, pending TEXT, screenshot TEXT, mode TEXT, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS applications (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT UNIQUE, company TEXT, title TEXT,
  resume_variant TEXT, submitted_at REAL, mode TEXT, answers_hash TEXT, screenshot_paths TEXT, apply_url TEXT,
  description_text TEXT);
CREATE TABLE IF NOT EXISTS events (ts REAL, level TEXT, message TEXT);
"""
# Stages: ranked → prepared (awaiting approval) | waiting (questions / login / captcha) → approved → submitting →
# submitted | dry-run | needs-check | failed | rejected. "submitting" at startup means we crashed mid-submit:
# it becomes needs-check, never a second submission.
STAGES = ("ranked", "prepared", "waiting", "approved", "submitting", "submitted", "dry-run", "needs-check", "failed", "rejected")


class Store:
    def __init__(self, path=None):
        self.path = path or os.path.join(HOME, "applyloop.sqlite")
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self.con = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=30)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self.lock = threading.RLock()
        self.listeners = []
        with self.lock:
            self.con.execute("UPDATE pipeline SET stage='needs-check', reason='the app stopped during submission: check "
                             "whether it went through before retrying', updated_at=? WHERE stage='submitting'", (time.time(),))

    def close(self):
        self.con.close()

    def q(self, sql, *args):
        with self.lock:
            return [dict(r) for r in self.con.execute(sql, args)]

    def x(self, sql, *args):
        with self.lock:
            self.con.execute(sql, args)

    # -------------------------------------------------- settings

    def get(self, key):
        rows = self.q("SELECT value FROM settings WHERE key=?", key)
        return json.loads(rows[0]["value"]) if rows else DEFAULTS.get(key)

    def set(self, key, value):
        self.x("INSERT OR REPLACE INTO settings VALUES (?,?)", key, json.dumps(value))

    def settings(self):
        out = dict(DEFAULTS)
        for r in self.q("SELECT key, value FROM settings"):
            out[r["key"]] = json.loads(r["value"])
        return out

    # -------------------------------------------------- events (the UI's live log)

    def log(self, message, level="info"):
        ts = time.time()
        self.x("INSERT INTO events VALUES (?,?,?)", ts, level, message)
        for fn in list(self.listeners):
            fn({"ts": ts, "level": level, "message": message})

    def events(self, since=0, limit=200):
        return self.q("SELECT * FROM events WHERE ts > ? ORDER BY ts DESC LIMIT ?", since, limit)[::-1]

    # -------------------------------------------------- pipeline

    def upsert_ranked(self, job, fit, parts, variant):
        now = time.time()
        self.x("""INSERT INTO pipeline (job_id, company, title, apply_url, ats, location, description_text, fit, parts,
                  resume_variant, stage, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?, 'ranked', ?, ?)
                  ON CONFLICT(job_id) DO UPDATE SET fit=excluded.fit, parts=excluded.parts, updated_at=excluded.updated_at
                  WHERE pipeline.stage='ranked'""",
               job["id"], job["company"], job["title"], job["apply_url"], job["id"].split(":")[0], job.get("location"),
               job.get("description_text", ""), fit, json.dumps(parts), variant, now, now)

    def job(self, job_id):
        rows = self.q("SELECT * FROM pipeline WHERE job_id=?", job_id)
        return self._decode(rows[0]) if rows else None

    def jobs(self, stage=None, limit=500):
        rows = self.q("SELECT * FROM pipeline %s ORDER BY fit DESC, created_at LIMIT ?" % ("WHERE stage=?" if stage else ""),
                      *([stage] if stage else []), limit)
        return [self._decode(r) for r in rows]

    @staticmethod
    def _decode(r):
        for k in ("parts", "fields", "answers", "pending"):
            r[k] = json.loads(r[k]) if r.get(k) else None
        return r

    def move(self, job_id, stage, reason=None, **cols):
        assert stage in STAGES, stage
        sets = ["stage=?", "reason=?", "updated_at=?"]
        args = [stage, reason, time.time()]
        for k, v in cols.items():
            sets.append("%s=?" % k)
            args.append(json.dumps(v) if k in ("fields", "answers", "pending") else v)
        self.x("UPDATE pipeline SET %s WHERE job_id=?" % ", ".join(sets), *args, job_id)

    def counts(self):
        return {r["stage"]: r["n"] for r in self.q("SELECT stage, COUNT(*) n FROM pipeline GROUP BY stage")}

    # -------------------------------------------------- applications (read by ghosted)

    def record_application(self, job, mode, answers_hash, screenshots):
        self.x("""INSERT OR IGNORE INTO applications (job_id, company, title, resume_variant, submitted_at, mode,
                  answers_hash, screenshot_paths, apply_url, description_text) VALUES (?,?,?,?,?,?,?,?,?,?)""",
               job["job_id"], job["company"], job["title"], job["resume_variant"], time.time(), mode, answers_hash,
               json.dumps(screenshots), job["apply_url"], job.get("description_text") or "")

    def submitted_today(self, now=None):
        now = now or time.time()
        return self.q("SELECT COUNT(*) n FROM applications WHERE submitted_at > ?", now - 86400)[0]["n"]

    def applied_to_company_since(self, company, since):
        return self.q("SELECT COUNT(*) n FROM applications WHERE lower(company)=lower(?) AND submitted_at > ?", company, since)[0]["n"] > 0
