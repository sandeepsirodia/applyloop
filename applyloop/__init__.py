"""applyloop: it applied while I slept, then told me what I lack, from my own rejections.

A local job-search agent: finds openings (whatshiring), prepares each application from your resume and your
saved answers (answerbank), submits it in your own Chrome at a human pace (ratekeeper), and learns from the
replies (ghosted). A local web UI shows everything live and lets you pause, approve or auto-approve, add
roles and resumes, and answer new questions. Everything stays on your machine.
"""
import argparse
import json
import os
import sys
import time

__version__ = "0.1.0"


def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog="applyloop", description="A local job-search agent that learns from its outcomes.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="add your resume and the roles you want")
    i.add_argument("--resume", required=True)
    i.add_argument("--label", default="main")
    i.add_argument("--roles", required=True, help='comma-separated, e.g. "backend engineer, platform engineer"')
    i.add_argument("--remote-from", metavar="COUNTRY", help='remote jobs only, open to someone living in COUNTRY, e.g. "India"')
    r = sub.add_parser("resume", help="see what a parser gets from a resume")
    r.add_argument("path")
    u = sub.add_parser("ui", help="start the local UI (the worker starts paused and in dry-run mode)")
    u.add_argument("--port", type=int, default=8765)
    u.add_argument("--cdp-url", help="attach to a Chrome you started with --remote-debugging-port")
    u.add_argument("--profile-dir", help="Chrome user-data folder (default ~/.applyloop/chrome)")
    u.add_argument("--no-open", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args(argv)

    from .store import Store
    if a.cmd == "resume":
        from . import intake
        structured, found, doc = intake.intake(a.path)
        out.write("Extracted with %s. %d finding(s):\n" % (doc["extractor"], len(found)))
        for f in found:
            out.write("  • %s%s\n" % (f["message"], "\n      %s" % f["evidence"] if f.get("evidence") else ""))
        out.write("\nStructured:\n%s\n" % json.dumps(structured, indent=2))
        return 0
    store = Store()
    try:
        if a.cmd == "init":
            from .ui import add_resume_file
            res = add_resume_file(store, a.label, os.path.abspath(a.resume))
            store.set("roles", [x.strip() for x in a.roles.split(",") if x.strip()])
            if a.remote_from:
                store.set("remote", True)
                store.set("remote_from", a.remote_from)
            out.write("Added resume %s (%d parsing finding(s)) and %d role(s).\n" % (a.label, len(res["findings"]), len(store.get("roles"))))
            out.write("Next: `whatshiring fetch`, then `applyloop ui`. It starts in dry-run mode: forms are filled, never submitted.\n")
        elif a.cmd == "status":
            s = store.settings()
            out.write("state: %s · %s · submitted today: %d/%d\n" % (s["state"], "dry run" if s["dry_run"] else "live",
                                                                    store.submitted_today(), s["daily_cap"]))
            for k, v in sorted(store.counts().items()):
                out.write("  %-12s %d\n" % (k, v))
        elif a.cmd == "ui":
            from .pipeline import Browser, Loop
            from .ui import App
            store.set("state", "paused")
            loop = Loop(store=store, browser=Browser(user_data_dir=a.profile_dir, cdp_url=a.cdp_url))
            app = App(loop, a.port)
            server = app.serve()
            out.write("applyloop is running at %s\n(paused, dry run: nothing is submitted until you switch dry run off)\n" % app.url())
            out.flush()
            if not a.no_open:
                import webbrowser
                webbrowser.open(app.url())
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                loop.stop_thread()
                server.server_close()
    finally:
        store.close()
    return 0
