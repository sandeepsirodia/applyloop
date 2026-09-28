"""The loop: discover → rank → prepare → approve → submit → track, one step at a time, every step persisted."""
import json
import os
import re
import threading
import time
from urllib.parse import urlparse

import whatshiring
from answerbank import Bank
from ratekeeper import Keeper

from . import forms
from .store import HOME, Store

LEVELS = whatshiring.LEVEL_ORDER


class Browser:
    """One Playwright browser, owned by the worker thread (Playwright's sync API isn't thread-safe).
    Profile-agnostic: a dedicated profile folder (Chrome 136+ refuses automation on the default one), any
    other folder you point it at, or a Chrome you started yourself (cdp_url). Logins are filled by Chrome's own
    password manager; applyloop never reads cookies or the password store."""

    def __init__(self, user_data_dir=None, cdp_url=None, headless=False, channel="chrome"):
        self.user_data_dir = user_data_dir or os.path.join(HOME, "chrome")
        self.cdp_url, self.headless, self.channel = cdp_url, headless, channel
        self._pw = self._ctx = None

    def context(self):
        if self._ctx is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            if self.cdp_url:
                browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
                self._ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            else:
                try:
                    self._ctx = self._pw.chromium.launch_persistent_context(self.user_data_dir, channel=self.channel, headless=self.headless)
                except Exception:  # noqa: BLE001 (Chrome not installed: fall back to Playwright's Chromium)
                    self._ctx = self._pw.chromium.launch_persistent_context(self.user_data_dir, headless=self.headless)
        return self._ctx

    def page(self):
        ctx = self.context()
        return ctx.new_page()

    def close(self):
        if self._ctx is not None:
            try:
                self._ctx.close()
            finally:
                self._pw.stop()
                self._ctx = self._pw = None


def host(url):
    return urlparse(url).hostname or "unknown"


class Loop:
    def __init__(self, store=None, jobs_db=None, bank=None, keeper=None, browser=None, screens=None, clock=time.time):
        self.store = store or Store()
        self.jobs_db = jobs_db or whatshiring.DEFAULT_DB
        self.keeper = keeper or Keeper(os.path.join(HOME, "ratekeeper.sqlite"))
        self.browser = browser or Browser()
        self.screens = screens or os.path.join(HOME, "screens")
        os.makedirs(self.screens, exist_ok=True)
        self.clock = clock
        self._bank = bank
        self.thread, self.stop_event = None, threading.Event()

    # -------------------------------------------------- inputs

    @property
    def bank(self):
        if self._bank is None:
            self._bank = Bank(os.path.join(HOME, "answers.json"), resume_text=self._resume_text())
        return self._bank

    def resumes(self):
        return self.store.get("resumes") or {}

    def _resume_json(self, label):
        with open(self.resumes()[label]["json"], encoding="utf-8") as f:
            return json.load(f)

    def _resume_text(self):
        label = self.store.get("default_resume")
        return json.dumps(self._resume_json(label)) if label else ""

    def _skills(self, label):
        return set(whatshiring.skills_in(json.dumps(self._resume_json(label))))

    # -------------------------------------------------- discover and rank

    def discover(self):
        s = self.store.settings()
        if not s["roles"] or not s["default_resume"]:
            self.store.log("add at least one role and a resume first", "warn")
            return []
        now = self.clock()
        con = whatshiring.open_db(self.jobs_db)
        try:
            mine = set().union(*(self._skills(l) for l in self.resumes()))
            res = whatshiring.match(con, mine, s["roles"] + s["adjacent_accepted"], now, s["level"], s["remote"], s["location"], top=1000)
            descs = {r["id"]: r["description_text"] for r in con.execute("SELECT id, description_text FROM jobs")}
        finally:
            con.close()
        self.store.set("adjacent_suggested", [a for a in res["adjacent"] if a["family"] not in s["adjacent_accepted"]])
        cooldown = now - s["cooldown_days"] * 86400
        known = {r["job_id"] for r in self.store.q("SELECT job_id FROM pipeline")}
        eligible = [j for j in res["ranked"] if j["id"] not in known and j["company"].lower() not in {b.lower() for b in s["blocklist"]}
                    and not self.store.applied_to_company_since(j["company"], cooldown)]
        # Under target: widen within bounds (the adjacent roles you accepted are already in; then a lower threshold,
        # never below your floor), and say so instead of padding the day with poor matches.
        threshold, target = s["fit_threshold"], s["daily_target"]
        good = [j for j in eligible if j["score"] >= threshold]
        while len(good) < target and threshold - 0.05 >= s["fit_floor"] - 1e-9:
            threshold = round(threshold - 0.05, 2)
            good = [j for j in eligible if j["score"] >= threshold]
        for j in good[:target]:
            variant = self._best_variant(j)
            self.store.upsert_ranked(dict(j, description_text=descs.get(j["id"], "")), j["score"], j["parts"], variant)
        if len(good) < target:
            self.store.log("only %d good matches today (target %d, floor %.2f)" % (len(good), target, s["fit_floor"]), "warn")
        elif threshold < s["fit_threshold"]:
            self.store.log("widened the fit threshold to %.2f to reach %d matches" % (threshold, target))
        else:
            self.store.log("ranked %d new matches" % min(len(good), target))
        return good[:target]

    def _best_variant(self, job):
        labels = list(self.resumes())
        if len(labels) == 1:
            return labels[0]
        js = set(job["skills"])
        return max(labels, key=lambda l: (len(js & self._skills(l)), l == self.store.get("default_resume")))

    # -------------------------------------------------- prepare (fill, never submit)

    def _open(self, job):
        site = host(job["apply_url"])
        with self.keeper.slot(site):
            page = self.browser.page()
            page.goto(job["apply_url"], wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_selector("input, textarea, select", timeout=15000)
            except Exception:  # noqa: BLE001
                pass
        signal = self.keeper.observe(site, text=page.content(), url=page.url, captcha=forms.challenge_visible(page))
        if not signal and forms.looks_like_login(page):
            self.keeper.pause(site, reason="login page: log in in the browser window, then resume", needs_human=True)
            signal = "logged-out"
        return page, site, signal

    def _job_ctx(self, job):
        return {"company": job["company"], "title": job["title"], "description": job.get("description_text") or "",
                "country": self._country(job.get("location") or "")}

    @staticmethod
    def _country(location):
        loc = location.lower()
        if re.search(r"\b(us|usa|united states|ca|ny|tx|wa|ma|remote - us)\b", loc) or re.search(r", (ca|ny|tx|wa|ma|co|il)\b", loc):
            return "United States"
        for c in ("canada", "united kingdom", "india", "germany", "france", "netherlands", "ireland", "singapore", "australia"):
            if c in loc:
                return c.title()
        return None

    def _screenshot(self, page, job, what):
        path = os.path.join(self.screens, "%s-%s.png" % (re.sub(r"[^\w-]+", "_", job["job_id"]), what))
        page.screenshot(path=path, full_page=True)
        return path

    def prepare(self, job):
        page, site, signal = self._open(job)
        try:
            if signal:
                self.store.move(job["job_id"], "waiting", "%s on %s: needs you" % (signal, site))
                self.store.log("%s: %s on %s, paused that site" % (job["company"], signal, site), "warn")
                return "waiting"
            resume = self._resume_json(job["resume_variant"])
            fields = forms.extract(page)
            plan, pending = forms.answer_fields(page, fields, forms.profile_from_resume(resume), self.bank, self._job_ctx(job),
                                                self.resumes()[job["resume_variant"]]["file"])
            forms.fill(page, plan)
            shot = self._screenshot(page, job, "prepared")
        finally:
            page.close()
        if pending:
            self.store.move(job["job_id"], "waiting", "%d question(s) only you can answer" % len(pending),
                            fields=fields, answers=plan, pending=pending, screenshot=shot)
            self.store.log("%s — %s: waiting for %d answer(s)" % (job["company"], job["title"], len(pending)))
            return "waiting"
        self.store.move(job["job_id"], "prepared", None, fields=fields, answers=plan, pending=[], screenshot=shot)
        ok, reasons = self.auto_approvable(self.store.job(job["job_id"]))
        if ok:
            self.store.move(job["job_id"], "approved", "auto-approved", mode="auto")
            self.store.log("%s — %s: auto-approved (fit %.2f)" % (job["company"], job["title"], job["fit"]))
            return "approved"
        self.store.log("%s — %s: ready for your approval (%s)" % (job["company"], job["title"], "; ".join(reasons)))
        return "prepared"

    def auto_approvable(self, job):
        s = self.store.settings()
        reasons = []
        if not s["auto_approve"]:
            reasons.append("auto-approve is off")
        if s["kill_switch"]:
            reasons.append("kill switch is on")
        if job["fit"] < s["fit_threshold"]:
            reasons.append("fit %.2f is below %.2f" % (job["fit"], s["fit_threshold"]))
        if job["pending"]:
            reasons.append("unanswered questions")
        if any(a["source"] == "drafted" for a in job["answers"] or []) and not s["allow_drafted"]:
            reasons.append("contains a drafted answer")
        if job["company"].lower() in {b.lower() for b in s["blocklist"]}:
            reasons.append("company is on your block list")
        if self.store.applied_to_company_since(job["company"], self.clock() - s["cooldown_days"] * 86400):
            reasons.append("applied to %s in the last %d days" % (job["company"], s["cooldown_days"]))
        if self.store.submitted_today(self.clock()) >= s["daily_cap"]:
            reasons.append("daily cap of %d reached" % s["daily_cap"])
        if not (self.resumes().get(job["resume_variant"]) or {}).get("reviewed"):
            reasons.append("resume %s isn't marked reviewed" % job["resume_variant"])
        return not reasons, reasons

    # -------------------------------------------------- submit

    def submit(self, job):
        s = self.store.settings()
        if self.store.submitted_today(self.clock()) >= s["daily_cap"]:
            return "capped"
        if s["dry_run"]:
            self.store.move(job["job_id"], "dry-run", "dry run: filled, not submitted")
            self.store.log("%s — %s: dry run, filled but not submitted" % (job["company"], job["title"]))
            return "dry-run"
        self.store.move(job["job_id"], "submitting", None)  # a crash from here on becomes needs-check, never a resubmit
        page, site, signal = self._open(job)
        try:
            if signal:
                self.store.move(job["job_id"], "waiting", "%s on %s: needs you" % (signal, site))
                return "waiting"
            resume = self._resume_json(job["resume_variant"])
            plan, pending = forms.answer_fields(page, forms.extract(page), forms.profile_from_resume(resume), self.bank,
                                                self._job_ctx(job), self.resumes()[job["resume_variant"]]["file"])
            if pending or forms.answers_hash(plan) != forms.answers_hash(job["answers"] or []):
                self.store.move(job["job_id"], "prepared", "the form changed since you approved it: review again", answers=plan, pending=pending)
                return "prepared"
            forms.fill(page, plan)
            before = self._screenshot(page, job, "before-submit")
            ok, detail = forms.submit(page)
            after = self._screenshot(page, job, "after-submit")
        finally:
            page.close()
        if ok:
            self.store.record_application(job, job.get("mode") or "manual", forms.answers_hash(plan), [before, after])
            self.store.move(job["job_id"], "submitted", detail)
            self.store.log("%s — %s: submitted (%s)" % (job["company"], job["title"], detail))
            return "submitted"
        if detail == "captcha":
            self.keeper.observe(site, captcha=True)
            self.store.move(job["job_id"], "waiting", "CAPTCHA after submit: finish it in the browser, then mark it done")
            return "waiting"
        self.store.move(job["job_id"], "failed", detail)
        self.store.log("%s — %s: not submitted (%s)" % (job["company"], job["title"], detail), "warn")
        return "failed"

    # -------------------------------------------------- the worker

    def approve(self, job_id):
        self.store.move(job_id, "approved", "approved by you", mode="manual")

    def reject(self, job_id):
        self.store.move(job_id, "rejected", "rejected by you")

    def answered(self):
        """After you answer questions, jobs that were waiting on them get prepared again."""
        for j in self.store.jobs("waiting"):
            if j["pending"] and all(p.get("pending_id") for p in j["pending"]):
                open_ids = {p["id"] for p in self.bank.data["pending"]}
                if not any(p["pending_id"] in open_ids for p in j["pending"]):
                    self.store.move(j["job_id"], "ranked", "your answers are in: preparing again")

    def step(self):
        """One unit of work. Returns what it did, or None when there's nothing to do right now."""
        s = self.store.settings()
        if s["state"] != "running":
            return None
        for j in self.store.jobs("approved"):
            if s["kill_switch"] and j.get("mode") == "auto":
                self.store.move(j["job_id"], "prepared", "kill switch: auto-approval withdrawn")
                continue
            return ("submit", j["job_id"], self.submit(j))
        ranked = self.store.jobs("ranked")
        if ranked:
            return ("prepare", ranked[0]["job_id"], self.prepare(ranked[0]))
        return None

    def run(self, idle_sleep=5.0):
        self.stop_event.clear()
        try:
            while not self.stop_event.is_set():
                try:
                    did = self.step()
                except Exception as e:  # noqa: BLE001 (one bad page must not kill the loop)
                    self.store.log("error: %s" % e, "error")
                    did = None
                if did is None:
                    self.stop_event.wait(idle_sleep)
        finally:
            self.browser.close()

    def start_thread(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop_thread(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(30)
