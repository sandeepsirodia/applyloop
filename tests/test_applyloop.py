"""Tests map 1:1 to SPEC.md (E1..E14). Forms are local copies of the shapes of real Greenhouse, Lever and Ashby
application pages, served on 127.0.0.1 and driven by a real headless Chromium. Nothing leaves the machine."""
import base64
import functools
import http.server
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import whatshiring  # noqa: E402
from answerbank import Bank  # noqa: E402
from ratekeeper import Keeper  # noqa: E402

from applyloop import forms, intake  # noqa: E402
from applyloop.pipeline import Browser, Loop  # noqa: E402
from applyloop.store import Store  # noqa: E402
from applyloop.ui import App, add_resume_file  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
RESUME_MD = """Ada Lovelace
ada@example.com · +1 415 555 0100 · linkedin.com/in/ada-l
Experience
Senior Backend Engineer, Initech (2021-2026): Python, PostgreSQL, Kafka and AWS.
Education
BSc Computer Science
Skills
Python, Go, PostgreSQL, Kafka, AWS, Kubernetes
"""


class FakeModel:
    def __init__(self):
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return "I have built payment systems in Python for four years and want to do that at Initech."


class HeadlessBrowser(Browser):
    """The real Browser class, launched headless and without a persistent profile, for tests."""

    def context(self):
        if self._ctx is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch()
            self._ctx = self._browser.new_context()
        return self._ctx

    def close(self):
        if self._ctx is not None:
            self._browser.close()
            self._pw.stop()
            self._ctx = self._pw = None


def serve_fixtures():
    handler = functools.partial(type("Q", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None}), directory=FIX)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "http://127.0.0.1:%d" % server.server_port


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.base = serve_fixtures()
        cls.browser = HeadlessBrowser()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="applyloop-")
        self.store = Store(os.path.join(self.dir, "applyloop.sqlite"))
        self.addCleanup(self.store.close)
        path = os.path.join(self.dir, "resume.md")
        with open(path, "w") as f:
            f.write(RESUME_MD)
        add_resume_file(self.store, "main", path)
        self.store.set("roles", ["backend engineer"])
        self.model = FakeModel()
        self.bank = Bank(os.path.join(self.dir, "answers.json"), model=self.model, resume_text=RESUME_MD)
        self.keeper = Keeper(os.path.join(self.dir, "rk.sqlite"), {"127.0.0.1": {"min_gap": 0.0, "jitter": 0.0, "per_minute": None, "per_hour": None, "per_day": None}})
        self.addCleanup(self.keeper.close)
        self.jobs_db = os.path.join(self.dir, "jobs.sqlite")
        self.loop = Loop(self.store, self.jobs_db, self.bank, self.keeper, self.browser, os.path.join(self.dir, "screens"))

    def mark_reviewed(self):
        r = self.store.get("resumes")
        r["main"]["reviewed"] = True
        self.store.set("resumes", r)

    def add_job(self, fixture, fit=0.82, company="Acme", title="Backend Engineer", job_id=None):
        job = {"id": job_id or "fixture:%s:%s" % (company.lower(), fixture), "company": company, "title": title,
               "apply_url": "%s/%s.html" % (self.base, fixture), "location": "San Francisco, CA", "description_text": "Python and Kafka."}
        self.store.upsert_ranked(job, fit, {"skills": 1.0}, "main")
        return self.store.job(job["id"])

    def known_answers(self):
        self.bank.set("work_authorized[united states]", True)
        self.bank.set("needs_sponsorship", False)
        self.bank.set("notice_period", "30 days")


class TestForms(Base):
    def fill_fixture(self, name):
        page = self.browser.page()
        page.goto("%s/%s.html" % (self.base, name))
        fields = forms.extract(page)
        profile = forms.profile_from_resume(json.load(open(self.store.get("resumes")["main"]["json"])))
        plan, pending = forms.answer_fields(page, fields, profile, self.bank, {"company": "Acme", "country": "United States"},
                                            os.path.join(self.dir, "resume.md"))
        forms.fill(page, plan)
        return page, fields, plan, pending

    def test_greenhouse_shape_labels_comboboxes_and_invisible_captcha(self):
        self.known_answers()
        page, fields, plan, pending = self.fill_fixture("greenhouse")
        self.assertEqual(pending, [])
        by_q = {f["question"]: f for f in plan}
        self.assertEqual(by_q["First Name"]["value"], "Ada")
        self.assertEqual(by_q["LinkedIn Profile"]["value"], "https://linkedin.com/in/ada-l")
        self.assertEqual(by_q["Are you legally authorized to work in the United States?"]["value"], "Yes")
        self.assertEqual(page.input_value("#question_3"), "No")
        self.assertEqual(page.input_value("#question_4"), "30 days")
        self.assertFalse(any("recaptcha" in (f.get("name") or "") for f in fields), "the invisible reCAPTCHA is not a question")
        self.assertEqual(page.evaluate("window.submissions"), 0)
        page.close()

    def test_lever_shape_cards_radios_and_select(self):
        self.bank.set("needs_sponsorship", True)
        self.bank.set("years_experience[python]", 6)
        page, _, plan, pending = self.fill_fixture("lever")
        self.assertEqual(pending, [])
        self.assertTrue(page.is_checked('input[name="cards[abc][field0]"][value="Yes"]'))
        self.assertEqual(page.eval_on_selector('select', "s => s.value"), "5+")
        self.assertEqual(page.input_value('input[name="name"]'), "Ada Lovelace")
        page.close()

    def test_ashby_shape_yes_no_buttons_and_drafted_essay(self):
        self.bank.set("work_authorized[united states]", True)
        page, _, plan, pending = self.fill_fixture("ashby")
        self.assertEqual(pending, [])
        self.assertTrue(page.is_checked('input[name="q-auth"]'))
        essay = next(f for f in plan if f["question"].startswith("Why do you want"))
        self.assertEqual(essay["source"], "drafted")
        page.close()


class TestPipeline(Base):
    def test_e1_dry_run_fills_everything_and_never_submits(self):
        self.known_answers()
        job = self.add_job("greenhouse")
        self.assertEqual(self.loop.prepare(job), "prepared")
        job = self.store.job(job["job_id"])
        self.assertTrue(os.path.exists(job["screenshot"]))
        self.assertEqual(len([a for a in job["answers"] if a["kind"] != "file"]), 8)
        self.assertIn("file", [a["kind"] for a in job["answers"]], "the resume is planned for the file field...")
        self.loop.approve(job["job_id"])
        self.assertEqual(self.loop.submit(self.store.job(job["job_id"])), "dry-run")
        self.assertEqual(self.store.q("SELECT COUNT(*) n FROM applications")[0]["n"], 0)

    def test_e2_new_question_waits_then_continues_after_answering(self):
        self.bank.set("work_authorized[united states]", True)
        self.bank.set("needs_sponsorship", False)
        job = self.add_job("greenhouse")
        self.assertEqual(self.loop.prepare(job), "waiting")
        (q,) = self.bank.data["pending"]
        self.assertEqual(q["question"], "What is your notice period?")
        self.bank.resolve(q["id"], "30 days")
        self.loop.answered()
        self.assertEqual(self.store.job(job["job_id"])["stage"], "ranked")
        self.assertEqual(self.loop.prepare(self.store.job(job["job_id"])), "prepared")

    def test_e3_auto_approve_submits_without_a_human(self):
        self.known_answers()
        self.mark_reviewed()
        self.store.set("auto_approve", True)
        self.store.set("dry_run", False)
        self.store.set("state", "running")
        job = self.add_job("greenhouse", fit=0.82)
        self.assertEqual(self.loop.step()[2], "approved")
        self.assertEqual(self.loop.step()[2], "submitted")
        app = self.store.q("SELECT * FROM applications")[0]
        self.assertEqual((app["company"], app["mode"], app["resume_variant"]), ("Acme", "auto", "main"))
        self.assertEqual(len(json.loads(app["screenshot_paths"])), 2)
        self.assertIsNone(self.loop.step(), "nothing left to do")
        self.assertEqual(self.store.job(job["job_id"])["stage"], "submitted")

    def test_e4_a_drafted_answer_blocks_auto_approval(self):
        self.bank.set("work_authorized[united states]", True)
        self.mark_reviewed()
        self.store.set("auto_approve", True)
        job = self.add_job("ashby", company="Initech", title="ML Engineer")
        self.assertEqual(self.loop.prepare(job), "prepared")
        ok, reasons = self.loop.auto_approvable(self.store.job(job["job_id"]))
        self.assertFalse(ok)
        self.assertIn("contains a drafted answer", reasons)

    def test_e5_kill_switch_withdraws_auto_approvals(self):
        job = self.add_job("greenhouse")
        self.store.move(job["job_id"], "approved", "auto-approved", mode="auto")
        self.store.set("state", "running")
        self.store.set("kill_switch", True)
        self.assertIsNone(self.loop.step())
        self.assertEqual(self.store.job(job["job_id"])["stage"], "prepared")

    def test_e6_crash_mid_submit_is_never_resubmitted(self):
        job = self.add_job("greenhouse")
        self.store.move(job["job_id"], "submitting")
        restarted = Store(self.store.path)
        self.addCleanup(restarted.close)
        j = restarted.job(job["job_id"])
        self.assertEqual(j["stage"], "needs-check")
        self.assertIn("check whether it went through", j["reason"])

    def test_e7_captcha_pauses_that_site_only(self):
        job = self.add_job("captcha")
        self.assertEqual(self.loop.prepare(job), "waiting")
        self.assertEqual(self.keeper.next_allowed("127.0.0.1"), float("inf"))
        self.assertLess(self.keeper.next_allowed("jobs.lever.co"), float("inf"))
        self.assertIn("captcha", self.store.job(job["job_id"])["reason"])

    def test_closed_posting_is_failed_not_prepared(self):
        job = self.add_job("closed")
        self.assertEqual(self.loop.prepare(job), "failed")
        self.assertIn("posting closed", self.store.job(job["job_id"])["reason"])

    def test_greenhouse_jobs_open_the_boards_own_form(self):
        self.assertEqual(Loop.form_url({"job_id": "greenhouse:databricks:8679982002", "apply_url": "https://databricks.com/x?gh_jid=8679982002"}),
                         "https://job-boards.greenhouse.io/databricks/jobs/8679982002")

    def test_e8_login_page_pauses_and_never_types_a_password(self):
        job = self.add_job("login")
        self.assertEqual(self.loop.prepare(job), "waiting")
        j = self.store.job(job["job_id"])
        self.assertIsNone(j["answers"], "nothing was filled on a login page")
        self.assertIn("logged-out", j["reason"])

    def test_e9_under_target_widens_to_the_floor_and_says_so(self):
        con = whatshiring.open_db(self.jobs_db)
        mk = lambda i, skills: whatshiring.make_job("greenhouse", "co%d" % i, i, "Co%d" % i, "Backend Engineer", "Remote",  # noqa: E731
                                                     "u", "%s/greenhouse.html" % self.base, time.time(), skills)
        jobs = [mk(i, "Python, Go, PostgreSQL, Kafka, AWS") for i in range(4)] + \
               [mk(10 + i, "Python, Java, Spring, Oracle, Scala") for i in range(4)] + \
               [mk(20 + i, "Haskell, OCaml, Erlang, Elixir, Clojure") for i in range(4)]
        for j in jobs:
            whatshiring.save_org(con, "greenhouse", j["org"], [j], time.time())
        con.commit()
        con.close()
        self.store.set("daily_target", 10)
        self.store.set("fit_threshold", 0.75)
        self.store.set("fit_floor", 0.55)
        picked = self.loop.discover()
        self.assertTrue(all(j["score"] >= 0.55 for j in picked))
        self.assertLess(len(picked), 10)
        self.assertGreater(len(picked), 4, "the floor let in the weaker Java matches, not the Haskell ones")
        self.assertIn("only %d good matches today (target 10, floor 0.55)" % len(picked), self.store.events()[-1]["message"])

    def test_remote_from_keeps_only_remote_jobs_open_to_you(self):
        con = whatshiring.open_db(self.jobs_db)
        mk = lambda i, loc, desc="Python, Go, PostgreSQL, Kafka, AWS": whatshiring.make_job(  # noqa: E731
            "greenhouse", "co%d" % i, i, "Co%d" % i, "Backend Engineer", loc, "u", "%s/greenhouse.html" % self.base, time.time(), desc)
        for i, (loc, desc) in enumerate([("Remote - India", None), ("Remote - US", None), ("Hybrid - Bengaluru", None),
                                          ("Remote", None), ("Remote", "Python, Go, Kafka. You must be located in the United States.")]):
            j = mk(i, loc, desc) if desc else mk(i, loc)
            whatshiring.save_org(con, "greenhouse", j["org"], [j], time.time())
        con.commit()
        con.close()
        self.store.set("remote", True)
        self.store.set("remote_from", "India")
        self.store.set("fit_floor", 0.0)
        picked = {j["location"]: j for j in self.loop.discover()}
        self.assertEqual(sorted(picked), ["Remote", "Remote - India"])
        self.assertIn("check it's open to someone in India", self.store.job(picked["Remote"]["id"])["reason"])

    def test_e11_uploaded_resume_needs_review_before_auto_approval(self):
        self.known_answers()
        self.store.set("auto_approve", True)
        job = self.add_job("greenhouse")
        self.loop.prepare(job)
        ok, reasons = self.loop.auto_approvable(self.store.job(job["job_id"]))
        self.assertIn("resume main isn't marked reviewed", reasons)
        self.mark_reviewed()
        self.assertTrue(self.loop.auto_approvable(self.store.job(job["job_id"]))[0])

    def test_e12_attaches_to_a_chrome_you_started(self):
        # "You started" Chrome: launched here with a debugging port. The attaching Browser runs in its own thread,
        # as applyloop's worker does (Playwright's sync API allows one instance per thread).
        self.browser.context()
        chrome = self.browser._pw.chromium.launch(args=["--remote-debugging-port=9337"])
        titles = []

        def attach():
            attached = Browser(cdp_url="http://127.0.0.1:9337")
            page = attached.page()
            page.goto("%s/greenhouse.html" % self.base)
            titles.append(page.title())
            attached._pw.stop()
        t = threading.Thread(target=attach)
        t.start()
        t.join(60)
        chrome.close()
        self.assertEqual(titles, ["Backend Engineer at Acme"])


class TestUI(Base):
    def test_e10_token_and_origin_are_required(self):
        app = App(self.loop, port=0)
        server = app.serve()
        app.port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        base = "http://127.0.0.1:%d" % app.port

        def get(path, headers=None):
            req = urllib.request.Request(base + path, headers=headers or {})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()
        self.assertEqual(get("/api/state")[0], 403)
        self.assertEqual(get("/api/state?t=wrong")[0], 403)
        self.assertEqual(get("/api/state", {"X-Token": app.token, "Origin": "https://evil.example"})[0], 403)
        self.assertEqual(get("/api/state", {"X-Token": app.token, "Host": "evil.example:%d" % app.port})[0], 403)
        code, body = get("/api/state", {"X-Token": app.token})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["settings"]["roles"], ["backend engineer"])
        code, page = get("/?t=" + app.token)
        self.assertEqual(code, 200)
        self.assertNotIn(b"innerHTML", page, "page data is never turned into HTML")
        page = self.browser.page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "/?t=" + app.token)
        page.wait_for_selector("#tabs button")
        page.click("#tabs >> text=Roles & resumes")
        self.assertEqual(errors, [], "the page runs without a single JavaScript error")
        self.assertIn("backend engineer", page.inner_text("#roleList"))
        self.assertTrue(page.locator("#kill").is_hidden(), "the kill-switch badge only shows when it's on")
        page.close()
        data = json.dumps({"label": "v2", "filename": "cv.md", "data": base64.b64encode(RESUME_MD.encode()).decode()}).encode()
        req = urllib.request.Request(base + "/api/resume", data, {"X-Token": app.token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            self.assertEqual(json.loads(r.read())["label"], "v2")
        self.assertFalse(self.store.get("resumes")["v2"]["reviewed"])


class TestIntake(Base):
    def test_e13_two_column_pdf_and_header_only_contact(self):
        page = self.browser.page()
        page.set_content("<html><body style='font:12px sans-serif;margin:40px'><div style='display:flex;gap:60px'>"
                         "<div style='width:40%'>" + "<p>Left column experience line about Python systems</p>" * 20 + "</div>"
                         "<div style='width:40%'>" + "<p>Right column skills line with Kubernetes and Go</p>" * 20 + "</div></div></body></html>")
        pdf = os.path.join(self.dir, "two-col.pdf")
        page.pdf(path=pdf)
        page.close()
        _, found, _ = intake.intake(pdf)
        self.assertIn("columns", [f["kind"] for f in found])
        self.assertIn("columns may be read out of order", " ".join(f["message"] for f in found))
        docx = os.path.join(self.dir, "header.docx")
        body = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                '<w:p><w:r><w:t>Ada Lovelace</w:t></w:r></w:p><w:p><w:r><w:t>Experience</w:t></w:r></w:p></w:body></w:document>')
        header = ('<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r>'
                  '<w:t>ada@example.com</w:t></w:r></w:p></w:hdr>')
        with zipfile.ZipFile(docx, "w") as z:
            z.writestr("word/document.xml", body)
            z.writestr("word/header1.xml", header)
        _, found, _ = intake.intake(docx)
        hidden = next(f for f in found if f["kind"] == "contact-hidden")
        self.assertEqual((hidden["message"], hidden["evidence"]), ("contact details only in the page header: many parsers skip it", "ada@example.com"))

    def test_e14_structuring_is_deterministic_and_never_invents(self):
        path = os.path.join(self.dir, "resume.md")
        a, _, doc = intake.intake(path)
        b, _, _ = intake.intake(path)
        self.assertEqual(a, b)
        self.assertEqual(a["basics"]["name"], "Ada Lovelace")
        self.assertEqual(intake.verify_against_source(a, doc["text"]), [])
        invented = dict(a, basics=dict(a["basics"], name="Ada Lovelace", label="Principal Engineer at Google"))
        self.assertEqual(intake.verify_against_source(invented, doc["text"]), [("basics.label", "Principal Engineer at Google")])


if __name__ == "__main__":
    unittest.main()
