"""Reading and filling application forms in a real browser.

One label-driven extractor covers the four shapes found on real Greenhouse, Lever and Ashby forms (Sept 2026):
plain inputs with <label for>, custom dropdowns (role=combobox, options only visible once opened), Lever-style
question cards with radio groups, and Ashby-style Yes/No buttons. Standard contact fields come from your resume;
every other question goes to answerbank, which answers from what you told it or queues the question for you.
Nothing here ever clicks submit except `submit()`, and nothing ever types a password.
"""
import hashlib
import json
import re

EXTRACT_JS = r"""
() => {
  const clean = s => (s || '').replace(/[\*✱]/g, '').replace(/\(required\)/i, '').replace(/\s+/g, ' ').trim();
  // Real Greenhouse forms pair each dropdown with a zero-size, transparent required <input>: not a question.
  const visible = e => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
                         return r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none' && cs.opacity !== '0'; };
  const container = e => e.closest('.application-question, [class*="question"], fieldset, [class*="field"], .form-group, li');
  const labelOf = e => {
    if (e.id) { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l && clean(l.innerText)) return clean(l.innerText); }
    const by = e.getAttribute('aria-labelledby');
    if (by) { const t = by.split(' ').map(x => (document.getElementById(x) || {}).innerText || '').join(' '); if (clean(t)) return clean(t); }
    if (e.getAttribute('aria-label') && !['Search'].includes(e.getAttribute('aria-label'))) return clean(e.getAttribute('aria-label'));
    const c = container(e);
    if (c) {
      const l = c.querySelector('label, legend, .application-label, [class*="label"], [class*="Label"]');
      if (l && clean(l.innerText)) return clean(l.innerText).split(' Yes No')[0];
    }
    const own = e.closest('label'); if (own) return clean(own.innerText);
    return '';
  };
  const optionLabel = e => {
    if (e.id) { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) return clean(l.innerText); }
    const own = e.closest('label'); if (own) return clean(own.innerText);
    return clean(e.value);
  };
  const fields = [], seenGroups = new Set();
  let n = 0;
  const tag = (e) => { const uid = 'al' + (n++); e.setAttribute('data-applyloop', uid); return uid; };
  for (const e of document.querySelectorAll('input, select, textarea, [role="combobox"]')) {
    const type = (e.getAttribute('type') || e.tagName).toLowerCase();
    if (['hidden', 'submit', 'button', 'search', 'image', 'reset'].includes(type)) continue;
    if (/recaptcha|hcaptcha|turnstile/i.test(e.name || '') || e.closest('.iti__country-list, [class*="country-list"]')) continue;
    if (e.getAttribute('role') !== 'combobox' && e.tagName === 'INPUT' && !e.id && !e.name && e.required && !visible(e)) continue;
    const required = !!(e.required || e.getAttribute('aria-required') === 'true');
    if (type === 'radio' || type === 'checkbox') {
      const key = e.name || e.id;
      if (seenGroups.has(key)) continue;
      seenGroups.add(key);
      const group = e.name ? Array.from(document.querySelectorAll('input[name="' + CSS.escape(e.name) + '"]')) : [e];
      const c = container(e);
      const buttons = c ? Array.from(c.querySelectorAll('button')).filter(b => /^(yes|no)$/i.test(clean(b.innerText))) : [];
      if (buttons.length) {  // Ashby: a hidden checkbox driven by Yes/No buttons
        const uid = tag(c);
        buttons.forEach(b => b.setAttribute('data-applyloop-option', uid));
        fields.push({uid, kind: 'buttons', question: labelOf(e), required, options: buttons.map(b => clean(b.innerText))});
        continue;
      }
      const uid = tag(e);
      group.forEach((g, i) => g.setAttribute('data-applyloop-option', uid + ':' + i));
      const single = type === 'checkbox' && group.length === 1;
      fields.push({uid, kind: single ? 'consent' : type, question: single ? labelOf(e) || optionLabel(e) : labelOf(e),
                   required, options: single ? [] : group.map(optionLabel)});
      continue;
    }
    if (!visible(e) && type !== 'file') continue;
    const uid = tag(e);
    if (e.getAttribute('role') === 'combobox') {
      fields.push({uid, kind: 'combobox', question: labelOf(e), required, options: null});
    } else if (e.tagName === 'SELECT') {
      const opts = Array.from(e.options).map(o => clean(o.text)).filter(t => t && !/^(select|choose|--|please select)/i.test(t));
      fields.push({uid, kind: 'select', question: labelOf(e), required, options: opts});
    } else {
      fields.push({uid, kind: type === 'textarea' ? 'textarea' : type, question: labelOf(e), required, options: null,
                   name: e.name || '', id: e.id || ''});
    }
  }
  return fields;
}
"""

# Standard fields come straight from your resume's contact details. Checked before answerbank.
PROFILE_FIELDS = [
    ("first_name", r"^(legal )?first name|^given name"), ("last_name", r"^(legal )?last name|^surname|^family name"),
    ("preferred_name", r"^preferred (first )?name"), ("name", r"^(full |legal )?name$"), ("email", r"^e-?mail( address)?$"),
    ("phone", r"^(mobile |cell )?phone( number)?$"), ("linkedin", r"linkedin"), ("github", r"github"),
    ("website", r"^(personal )?(website|portfolio)( url)?$|^other website"), ("location", r"^(current )?location$|^city$"),
    ("current_company", r"^(current|most recent) (company|employer)|^company$"),
    ("current_title", r"^(current|most recent) (job )?(title|role|position)"),
]
PROFILE_FIELDS = [(k, re.compile(rx, re.I)) for k, rx in PROFILE_FIELDS]
RESUME_FILE_RE = re.compile(r"resume|\bcv\b|curriculum", re.I)
SUBMIT_RE = re.compile(r"^\s*(submit( application| your application)?|send application|apply( now)?)\s*$", re.I)
SUCCESS_RE = re.compile(r"thank you for (applying|your application|your interest)|application (has been |was )?(submitted|received)|"
                        r"we('ve| have) received your application|thanks for applying", re.I)
CHALLENGE_FRAME_RE = re.compile(r"recaptcha/(api2|enterprise)/bframe|hcaptcha\.com/.*(challenge|frame=challenge)|challenges\.cloudflare\.com", re.I)


def profile_from_resume(resume):
    b = resume.get("basics", {})
    name = (b.get("name") or "").strip()
    first, _, last = name.partition(" ")
    urls = {p.get("network", "").lower(): p.get("url") for p in b.get("profiles") or []}
    work = (resume.get("work") or [{}])[0]
    loc = b.get("location") or {}
    return {k: v for k, v in {
        "name": name, "first_name": first, "last_name": last.split(" ")[-1] if last else "", "preferred_name": first,
        "email": b.get("email"), "phone": b.get("phone"), "linkedin": urls.get("linkedin"), "github": urls.get("github"),
        "website": b.get("url"), "location": ", ".join(x for x in (loc.get("city"), loc.get("region")) if x) or None,
        "current_company": work.get("name"), "current_title": work.get("position")}.items() if v}


CLOSED_RE = re.compile(r"page not found|(job|position|posting|role) (is )?no longer (available|open|accepting)|"
                       r"no longer accepting applications|this (job|position) has (been filled|closed)|job not found", re.I)


def posting_closed(page):
    try:
        m = CLOSED_RE.search(page.inner_text("body")[:3000])
    except Exception:  # noqa: BLE001
        return None
    return "posting closed (the page says: %s)" % m.group(0) if m else None


def extract(page):
    return page.evaluate(EXTRACT_JS)


def open_combobox(page, field):
    """Custom dropdowns only reveal their options when opened."""
    box = page.locator('[data-applyloop="%s"]' % field["uid"])
    box.click()
    page.wait_for_timeout(150)
    opts = []
    for o in page.locator('[role="option"]:visible').all_inner_texts():  # only this dropdown's open list
        if o.strip() and o.strip() not in opts:
            opts.append(o.strip())
    page.keyboard.press("Escape")
    return opts


def answer_fields(page, fields, profile, bank, job, resume_path):
    """Decide every field's value. Returns (plan, pending): plan entries say what will be filled and where it
    came from (profile | answerbank:<how> | drafted | file); pending lists questions only you can answer."""
    plan, pending = [], []
    for f in fields:
        q = f["question"]
        if f["kind"] == "file":
            if RESUME_FILE_RE.search(q + " " + f.get("id", "") + " " + f.get("name", "")):
                plan.append(dict(f, value=resume_path, source="file"))
            elif f["required"]:
                pending.append(dict(f, reason="a required file upload that isn't your resume"))
            continue
        key = next((k for k, rx in PROFILE_FIELDS if rx.search(q)), None) if f["kind"] in ("text", "email", "tel", "url") else None
        if key and profile.get(key):
            plan.append(dict(f, value=profile[key], source="profile"))
            continue
        if f["kind"] == "combobox" and f["options"] is None:
            f["options"] = open_combobox(page, f)
        options = f["options"] if f["kind"] in ("select", "radio", "checkbox", "combobox", "buttons") and f["options"] else None
        if f["kind"] == "consent":
            options = None
        if not q:
            if f["required"]:
                pending.append(dict(f, reason="a required field with no label applyloop can read"))
            continue
        res = bank.answer(q, options, job)
        if res["status"] == "answered":
            plan.append(dict(f, value=res["text"], source="drafted" if res["drafted"] else "answerbank:" + res["how"], key=res["key"]))
        elif f["required"]:
            pending.append(dict(f, reason=res["reason"], pending_id=res.get("id")))
        # optional and unknown: left blank (still queued in answerbank, so answering it once fills it next time)
    return plan, pending


def fill(page, plan, upload=False):
    """Fill the form. Files are attached only when `upload` is set (at submit): some forms, Greenhouse's among them,
    send an attachment to the company the moment it's selected, before any submit."""
    for f in plan:
        sel = '[data-applyloop="%s"]' % f["uid"]
        v = f["value"]
        k = f["kind"]
        if k == "file":
            if upload:
                page.set_input_files(sel, v)
        elif k in ("text", "email", "tel", "url", "textarea", "number"):
            page.fill(sel, str(v))
        elif k == "select":
            page.select_option(sel, label=v)
        elif k in ("radio", "checkbox"):
            i = f["options"].index(v)
            page.check('[data-applyloop-option="%s:%d"]' % (f["uid"], i))
        elif k == "consent":
            if str(v).lower() in ("yes", "true"):
                page.check(sel)
        elif k == "buttons":
            page.locator('[data-applyloop-option="%s"]' % f["uid"]).filter(has_text=re.compile(r"^\s*%s\s*$" % re.escape(v), re.I)).first.click()
        elif k == "combobox":
            page.click(sel)
            page.locator('[role="option"]:visible').filter(has_text=re.compile(r"^\s*%s\s*$" % re.escape(v))).first.click()


def answers_hash(plan):
    return hashlib.sha256(json.dumps(sorted((f["question"], str(f["value"])) for f in plan)).encode()).hexdigest()[:16]


def challenge_visible(page):
    """A CAPTCHA the user is actually being shown (an embedded invisible widget doesn't count)."""
    for fr in page.frames:
        if CHALLENGE_FRAME_RE.search(fr.url or ""):
            try:
                el = fr.frame_element()
                if el.is_visible() and (el.bounding_box() or {}).get("height", 0) > 60:
                    return True
            except Exception:  # noqa: BLE001 (detached frames)
                continue
    return False


def looks_like_login(page):
    return page.locator('input[type="password"]').count() > 0 and page.locator('input[type="file"]').count() == 0


def submit(page, timeout=20000):
    """Click the form's submit button and wait for a confirmation. Returns (ok, detail)."""
    buttons = page.locator('button, input[type="submit"]')
    target = None
    for i in range(buttons.count()):
        b = buttons.nth(i)
        text = (b.inner_text() if b.evaluate("e => e.tagName") == "BUTTON" else b.get_attribute("value")) or ""
        if SUBMIT_RE.match(text) and b.is_visible():
            target = b
    if target is None:
        return False, "no submit button found"
    before = page.url
    target.click()
    try:
        page.wait_for_function("() => /thank you for (applying|your application|your interest)|application (has been |was )?(submitted|received)|"
                               "received your application|thanks for applying/i.test(document.body.innerText)", timeout=timeout)
        return True, "confirmation shown"
    except Exception:  # noqa: BLE001 (timeout)
        if challenge_visible(page):
            return False, "captcha"
        if page.url != before and SUCCESS_RE.search(page.inner_text("body")):
            return True, "confirmation page"
        return False, "no confirmation after submitting"
