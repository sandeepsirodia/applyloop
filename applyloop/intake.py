"""Resume intake: any resume → what a text parser actually gets from it, plus a reviewed JSON Resume file.

Hiring systems read your resume as extracted text before a person does. Two-column layouts, icon fonts,
letter-spaced headings and contact details tucked in a page header often come out scrambled or missing.
Every finding quotes the text as evidence. There is deliberately no "ATS score": there is no single ATS.
"""
import hashlib
import html
import json
import os
import re
import zipfile

from whatshiring import skills_in

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d ().-]{7,}\d)(?!\d)")
URL_RE = re.compile(r"(?:https?://)?(?:www\.)?(linkedin\.com/in/[\w-]+|github\.com/[\w-]+)[/\w-]*", re.I)
HEADINGS = {"experience": r"(work |professional )?experience|employment( history)?",
            "education": r"education|academic", "skills": r"(technical )?skills|technologies|tech stack"}
SPACED_RE = re.compile(r"\b(?:[A-Za-z] ){3,}[A-Za-z]\b")
BAD_GLYPH_RE = re.compile("[-�□]")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# ------------------------------------------------------------------ reading

def _docx_text(xml_bytes):
    """Paragraph text from a WordprocessingML part, and the text that sat inside text boxes."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_bytes)
    boxed = set()
    for box in root.iter(W + "txbxContent"):
        for p in box.iter(W + "p"):
            boxed.add(id(p))
    main, box_text = [], []
    for p in root.iter(W + "p"):
        t = "".join(x.text or "" for x in p.iter(W + "t"))
        if t.strip():
            (box_text if id(p) in boxed else main).append(t)
    return main, box_text


def read_docx(path):
    with zipfile.ZipFile(path) as z:
        body, boxes = _docx_text(z.read("word/document.xml"))
        header = []
        for name in z.namelist():
            if re.match(r"word/(header|footer)\d*\.xml$", name):
                h, hb = _docx_text(z.read(name))
                header += h + hb
        tables = len(re.findall(rb"<w:tbl>", z.read("word/document.xml")))
    return {"text": "\n".join(body), "header": "\n".join(header), "boxes": "\n".join(boxes), "tables": tables,
            "extractor": "docx (standard library)"}


def read_pdf(path):
    try:
        import pdfplumber
    except ImportError:
        raise SystemExit("PDF resumes need pdfplumber: pip install 'applyloop[pdf]'") from None
    pages, columns = [], []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
            words = page.extract_words()
            columns.append(_column_gap(words, page.width))
            if not words and page.images:
                columns[-1] = "image-only"
    return {"text": "\n".join(pages), "header": "", "boxes": "", "tables": 0, "columns": columns, "extractor": "pdfplumber"}


def _column_gap(words, width):
    """An x-range (at least 3% of the page wide) that no word crosses, with plenty of words on both sides:
    the page is laid out in columns, and line-by-line extraction will interleave them."""
    if len(words) < 30:
        return None
    covered = [0] * int(width + 1)
    for w in words:
        for x in range(int(w["x0"]), min(int(w["x1"]) + 1, len(covered))):
            covered[x] += 1
    best, start = None, None
    for x in range(int(width * 0.15), int(width * 0.85)):
        if covered[x] == 0 and start is None:
            start = x
        elif covered[x] != 0 and start is not None:
            if x - start >= width * 0.03 and (best is None or x - start > best[1] - best[0]):
                best = (start, x)
            start = None
    if not best:
        return None
    left = sum(1 for w in words if w["x1"] <= best[0])
    right = sum(1 for w in words if w["x0"] >= best[1])
    return best if min(left, right) >= 0.2 * len(words) else None


def read_any(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return read_docx(path)
    if ext == ".pdf":
        return read_pdf(path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if ext == ".json":
        data = json.loads(text)
        return {"text": json.dumps(data, indent=1), "header": "", "boxes": "", "tables": 0, "extractor": "json", "json": data}
    return {"text": text, "header": "", "boxes": "", "tables": 0, "extractor": "text"}


# ------------------------------------------------------------------ findings

def findings(doc):
    out, text = [], doc["text"]
    for i, gap in enumerate(doc.get("columns") or []):
        if gap == "image-only":
            out.append({"kind": "image-text", "message": "page %d has images but no extractable text: a parser sees nothing there" % (i + 1)})
        elif gap:
            lines = [l for l in text.split("\n") if l.strip()][:3]
            out.append({"kind": "columns", "message": "page %d is laid out in columns: columns may be read out of order" % (i + 1),
                        "evidence": " / ".join(lines)})
    if doc.get("tables"):
        out.append({"kind": "columns", "message": "layout uses %d table(s): columns may be read out of order" % doc["tables"]})
    body_contact = EMAIL_RE.search(text) or PHONE_RE.search(text)
    elsewhere = EMAIL_RE.search(doc.get("header", "") + doc.get("boxes", "")) or PHONE_RE.search(doc.get("header", "") + doc.get("boxes", ""))
    if not body_contact and elsewhere:
        where = "the page header" if EMAIL_RE.search(doc.get("header", "")) or PHONE_RE.search(doc.get("header", "")) else "a text box"
        out.append({"kind": "contact-hidden", "message": "contact details only in %s: many parsers skip it" % where,
                    "evidence": elsewhere.group(0)})
    for m in SPACED_RE.finditer(text):
        out.append({"kind": "letter-spaced", "message": "letter-spaced text reads as separate letters",
                    "evidence": m.group(0), "suggest": m.group(0).replace(" ", "")})
        break
    bad = BAD_GLYPH_RE.findall(text)
    if bad:
        out.append({"kind": "glyphs", "message": "%d icon characters became unreadable symbols" % len(bad)})
    low = text.lower()
    missing = [k for k, rx in HEADINGS.items() if not re.search(r"(^|\n)\s*(%s)\s*:?\s*(\n|$)" % rx, low)]
    if missing and doc["extractor"] != "json":
        out.append({"kind": "headings", "message": "no standard section heading for: %s" % ", ".join(missing)})
    return out


# ------------------------------------------------------------------ structuring (rules; a model may only structure)

def structure(doc, source_path):
    if doc.get("json"):
        data = dict(doc["json"])
    else:
        text = doc["text"] + "\n" + doc.get("header", "") + "\n" + doc.get("boxes", "")
        lines = [l.strip() for l in doc["text"].split("\n") if l.strip()]
        name = next((l for l in lines[:5] if not EMAIL_RE.search(l) and not re.search(r"\d", l) and len(l.split()) <= 5), None)
        profiles = [{"network": "LinkedIn" if "linkedin" in m.group(0).lower() else "GitHub",
                     "url": "https://" + m.group(1)} for m in URL_RE.finditer(text)]
        email = EMAIL_RE.search(text)
        phone = PHONE_RE.search(text)
        data = {"basics": {k: v for k, v in {"name": name, "email": email.group(0) if email else None,
                                             "phone": phone.group(0).strip() if phone else None,
                                             "profiles": profiles or None}.items() if v},
                "x-skills-detected": skills_in(text),  # derived by matching, not a claim written in the resume
                "x-sections": _sections(doc["text"])}
    with open(source_path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    data["x-canon"] = {"source": os.path.basename(source_path), "sha256": sha, "extractor": doc["extractor"], "reviewed": False}
    return data


def _sections(text):
    out, current = {}, None
    for line in text.split("\n"):
        low = line.strip().lower().rstrip(":")
        hit = next((k for k, rx in HEADINGS.items() if re.fullmatch(rx, low)), None)
        if hit:
            current = hit
            out.setdefault(current, [])
        elif current and line.strip():
            out[current].append(line.strip())
    return out


def verify_against_source(structured, source_text):
    """Reject any string a model put in the structure that doesn't appear in the resume itself."""
    src = re.sub(r"\s+", " ", source_text.lower())
    unscheme = lambda v: re.sub(r"^https?://(www\.)?", "", v)  # noqa: E731 (adding https:// is normalising, not inventing)
    bad = []

    def walk(v, path):
        if isinstance(v, dict):
            for k, x in v.items():
                if not k.startswith("x-"):
                    walk(x, path + [k])
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, path + [str(i)])
        elif isinstance(v, str) and v.strip() and unscheme(re.sub(r"\s+", " ", v.lower().strip())) not in src:
            bad.append((".".join(path), v))
    walk(structured, [])
    return bad


def intake(path):
    doc = read_any(path)
    return structure(doc, path), findings(doc), doc


def review_html(structured, doc, found):
    rows = "".join("<li><b>%s</b>%s</li>" % (html.escape(f["message"]), "<br><code>%s</code>" % html.escape(f["evidence"])
                                             if f.get("evidence") else "") for f in found) or "<li>No problems found.</li>"
    return ("<!doctype html><meta charset=utf-8><title>Resume review</title><style>body{font:14px system-ui;margin:24px}"
            ".cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}pre{white-space:pre-wrap;background:#f6f8fa;padding:12px}"
            "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}pre{background:#1c1c1c}}</style>"
            "<h1>What a parser gets from your resume</h1><ul>%s</ul><div class=cols><div><h2>Extracted text (%s)</h2><pre>%s</pre>"
            "</div><div><h2>Structured (JSON Resume)</h2><pre>%s</pre></div></div>") % (
        rows, html.escape(doc["extractor"]), html.escape(doc["text"]), html.escape(json.dumps(structured, indent=2)))
