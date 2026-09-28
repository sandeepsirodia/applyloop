"""Seed a throwaway store with synthetic jobs and open the UI, for screenshots and trying it out.

    python examples/demo_ui.py            # prints a local URL; nothing is fetched or submitted
"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from answerbank import Bank  # noqa: E402
from ratekeeper import Keeper  # noqa: E402

from applyloop.pipeline import Loop  # noqa: E402
from applyloop.store import Store  # noqa: E402
from applyloop.ui import App, add_resume_file  # noqa: E402

RESUME = """Ada Lovelace
ada@example.com · +1 415 555 0100 · linkedin.com/in/ada-l
Experience
Senior Backend Engineer, Initech (2021-2026): Python, PostgreSQL, Kafka and AWS.
Education
BSc Computer Science
Skills
Python, Go, PostgreSQL, Kafka, AWS, Kubernetes
"""
JOBS = [("Globex", "Senior Backend Engineer", 0.91, "submitted", "confirmation shown"),
        ("Initech", "Platform Engineer", 0.86, "prepared", None),
        ("Hooli", "Backend Engineer, Payments", 0.81, "prepared", None),
        ("Umbrella", "Staff Software Engineer", 0.78, "waiting", "2 question(s) only you can answer"),
        ("Soylent", "Infrastructure Engineer", 0.74, "ranked", None),
        ("Vandelay", "Backend Engineer", 0.72, "dry-run", "dry run: filled, not submitted")]


def seed(folder):
    store = Store(os.path.join(folder, "applyloop.sqlite"))
    path = os.path.join(folder, "resume.md")
    with open(path, "w") as f:
        f.write(RESUME)
    add_resume_file(store, "backend-v2", path)
    store.set("roles", ["backend engineer", "platform engineer"])
    store.set("adjacent_suggested", [{"family": "infra", "median_cover": 0.62, "open": 212, "now": 48, "then": 31}])
    for company, title, fit, stage, reason in JOBS:
        jid = "greenhouse:%s:1" % company.lower()
        store.upsert_ranked({"id": jid, "company": company, "title": title, "apply_url": "https://example.com/jobs/1",
                             "location": "Remote - US"}, fit, {"skills": fit}, "backend-v2")
        answers = [{"question": "First Name", "value": "Ada", "source": "profile", "kind": "text"},
                   {"question": "Email", "value": "ada@example.com", "source": "profile", "kind": "email"},
                   {"question": "Are you legally authorized to work in the United States?", "value": "Yes", "source": "answerbank:pattern", "kind": "combobox"},
                   {"question": "Will you now or in the future require visa sponsorship?", "value": "No", "source": "answerbank:exact", "kind": "combobox"},
                   {"question": "Resume/CV", "value": path, "source": "file", "kind": "file"}]
        store.move(jid, stage, reason, answers=answers if stage != "ranked" else None, pending=[])
        if stage == "submitted":
            store.record_application(store.job(jid), "manual", "demo", [])
    for msg, level in [("ranked 6 new matches", "info"), ("Globex — Senior Backend Engineer: submitted (confirmation shown)", "info"),
                       ("Umbrella — Staff Software Engineer: waiting for 2 answer(s)", "info"),
                       ("jobs.lever.co: CAPTCHA shown: needs a human, paused that site", "warn")]:
        store.log(msg, level)
    bank = Bank(os.path.join(folder, "answers.json"))
    bank.answer("What is your notice period?", job={"company": "Umbrella"})
    bank.answer("How many years of experience do you have with Kafka?", ["0-2", "3-5", "5+"], {"company": "Umbrella"})
    keeper = Keeper(os.path.join(folder, "rk.sqlite"))
    for _ in range(3):
        keeper.try_slot("job-boards.greenhouse.io")
    keeper.pause("jobs.lever.co", reason="CAPTCHA shown: needs a human", needs_human=True)
    return Loop(store, os.path.join(folder, "jobs.sqlite"), bank, keeper, browser=None, screens=os.path.join(folder, "screens"))


if __name__ == "__main__":
    loop = seed(tempfile.mkdtemp(prefix="applyloop-demo-"))
    app = App(loop, port=int(os.environ.get("PORT", "8766")))
    server = app.serve()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(app.url(), flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()
