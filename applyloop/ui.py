"""The local UI: watch the pipeline live, approve, answer questions, add roles and resumes, pause sites.

Standard-library HTTP server bound to 127.0.0.1, with a random token per session. Requests without the token,
or whose Host/Origin isn't this machine (DNS rebinding, another site in your browser), are refused.
"""
import base64
import json
import os
import queue
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import intake
from .store import HOME

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui.html")


class App:
    def __init__(self, loop, port=8765, token=None):
        self.loop, self.port = loop, port
        self.token = token or secrets.token_urlsafe(24)
        self.subscribers = []
        loop.store.listeners.append(self._broadcast)

    def _broadcast(self, event):
        for q in list(self.subscribers):
            q.put(event)

    # -------------------------------------------------- state for the page

    def state(self):
        st, loop = self.loop.store, self.loop
        s = st.settings()
        approvals = [dict(j, screenshot_url="/screens/%s?t=%s" % (os.path.basename(j["screenshot"]), self.token) if j["screenshot"] else None,
                          auto=loop.auto_approvable(j)[1]) for j in st.jobs("prepared")]
        try:
            budgets = loop.keeper.status()
        except Exception:  # noqa: BLE001
            budgets = {"sites": {}}
        for v in budgets["sites"].values():
            v["next_allowed"] = None if v["next_allowed"] == float("inf") else v["next_allowed"]
        return {
            "settings": {k: v for k, v in s.items() if k != "profile"}, "counts": st.counts(),
            "submitted_today": st.submitted_today(), "approvals": approvals,
            "waiting": [{k: j[k] for k in ("job_id", "company", "title", "reason")} for j in st.jobs("waiting")],
            "recent": [{k: j[k] for k in ("job_id", "company", "title", "stage", "reason", "fit", "updated_at")}
                       for j in sorted(st.jobs(), key=lambda j: -(j["updated_at"] or 0))[:40]],
            "questions": loop.bank.data["pending"], "budgets": budgets, "events": st.events(limit=100),
            "outcomes": self.outcomes(),
        }

    def outcomes(self):
        n = self.loop.store.q("SELECT COUNT(*) n FROM applications")[0]["n"]
        report = os.path.join(HOME, "ghosted.html")
        return {"applications": n, "report": "/ghosted?t=%s" % self.token if os.path.exists(report) else None,
                "how": "ghosted run --apps %s --imap imap.gmail.com --user you@gmail.com --html %s" % (self.loop.store.path, report)}

    # -------------------------------------------------- actions

    def act(self, path, body):
        st, loop = self.loop.store, self.loop
        if path == "/api/control":
            a = body["action"]
            if a in ("start", "resume"):
                st.set("state", "running")
                loop.start_thread()
            elif a == "pause":
                st.set("state", "paused")
            elif a == "stop":
                st.set("state", "paused")
                loop.stop_thread()
            elif a == "discover":
                loop.discover()
            elif a in ("kill", "unkill"):
                st.set("kill_switch", a == "kill")
            st.log("control: %s" % a)
        elif path == "/api/settings":
            allowed = {"auto_approve", "fit_threshold", "fit_floor", "allow_drafted", "daily_cap", "daily_target", "cooldown_days",
                       "blocklist", "dry_run", "level", "remote", "location", "adjacent_accepted"}
            for k, v in body.items():
                if k not in allowed:
                    raise ValueError("unknown setting %s" % k)
                st.set(k, v)
        elif path == "/api/roles":
            roles = st.get("roles")
            if body.get("add") and body["add"] not in roles:
                roles.append(body["add"].strip())
            if body.get("remove"):
                roles = [r for r in roles if r != body["remove"]]
            st.set("roles", roles)
        elif path == "/api/approve":
            loop.approve(body["job_id"])
        elif path == "/api/reject":
            loop.reject(body["job_id"])
        elif path == "/api/answer":
            loop.bank.resolve(int(body["id"]), body["value"], body.get("when") or None)
            loop.answered()
        elif path == "/api/budget":
            (loop.keeper.pause if body["action"] == "pause" else loop.keeper.resume)(body["site"])
        elif path == "/api/resume":
            return self.add_resume(body["label"], body["filename"], base64.b64decode(body["data"]))
        elif path == "/api/resume/reviewed":
            resumes = st.get("resumes")
            resumes[body["label"]]["reviewed"] = True
            st.set("resumes", resumes)
        else:
            raise KeyError(path)
        return {"ok": True}

    def add_resume(self, label, filename, data):
        label = re.sub(r"[^\w.-]+", "-", label.strip()) or "resume"
        folder = os.path.join(HOME, "resumes")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "%s%s" % (label, os.path.splitext(filename)[1].lower()))
        with open(path, "wb") as f:
            f.write(data)
        return add_resume_file(self.loop.store, label, path)

    # -------------------------------------------------- server

    def handler(self):
        app = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _ok_origin(self):
                hostport = self.headers.get("Host", "")
                if hostport not in ("127.0.0.1:%d" % app.port, "localhost:%d" % app.port):
                    return False
                origin = self.headers.get("Origin")
                return origin in (None, "http://127.0.0.1:%d" % app.port, "http://localhost:%d" % app.port)

            def _authed(self, qs):
                tok = self.headers.get("X-Token") or (qs.get("t") or [None])[0]
                return self._ok_origin() and tok is not None and secrets.compare_digest(tok, app.token)

            def _send(self, code, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else (json.dumps(body, default=str) if ctype == "application/json" else body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Frame-Options", "DENY")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                u = urlparse(self.path)
                qs = parse_qs(u.query)
                if not self._authed(qs):
                    return self._send(403, {"error": "forbidden: open the link printed by `applyloop ui`"})
                if u.path == "/":
                    with open(PAGE, encoding="utf-8") as f:
                        return self._send(200, f.read().replace("__TOKEN__", app.token), "text/html; charset=utf-8")
                if u.path == "/api/state":
                    return self._send(200, app.state())
                if u.path.startswith("/screens/"):
                    name = os.path.basename(u.path)
                    path = os.path.join(app.loop.screens, name)
                    if not re.fullmatch(r"[\w.-]+\.png", name) or not os.path.exists(path):
                        return self._send(404, {"error": "no such screenshot"})
                    with open(path, "rb") as f:
                        return self._send(200, f.read(), "image/png")
                if u.path == "/ghosted":
                    with open(os.path.join(HOME, "ghosted.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                if u.path == "/api/events":
                    q = queue.Queue()
                    app.subscribers.append(q)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    try:
                        while True:
                            try:
                                ev = q.get(timeout=15)
                                self.wfile.write(("data: %s\n\n" % json.dumps(ev)).encode())
                            except queue.Empty:
                                self.wfile.write(b": keep-alive\n\n")
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    finally:
                        app.subscribers.remove(q)
                    return
                return self._send(404, {"error": "not found"})

            def do_POST(self):
                u = urlparse(self.path)
                if not self._authed(parse_qs(u.query)):
                    return self._send(403, {"error": "forbidden"})
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                    return self._send(200, app.act(u.path, body))
                except (KeyError, ValueError) as e:
                    return self._send(400, {"error": str(e)})

        return H

    def serve(self):
        server = ThreadingHTTPServer(("127.0.0.1", self.port), self.handler())
        server.daemon_threads = True
        return server

    def url(self):
        return "http://127.0.0.1:%d/?t=%s" % (self.port, self.token)


def add_resume_file(store, label, path):
    structured, found, doc = intake.intake(path)
    json_path = os.path.splitext(path)[0] + ".resume.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(structured, f, indent=2)
    with open(os.path.splitext(path)[0] + ".review.html", "w", encoding="utf-8") as f:
        f.write(intake.review_html(structured, doc, found))
    resumes = store.get("resumes")
    resumes[label] = {"file": os.path.abspath(path), "json": json_path, "reviewed": False, "findings": found, "added": time.time()}
    store.set("resumes", resumes)
    if not store.get("default_resume"):
        store.set("default_resume", label)
    store.log("resume %s added: %d finding(s)%s" % (label, len(found), "".join("; " + f["message"] for f in found[:3])))
    return {"ok": True, "label": label, "findings": found}
