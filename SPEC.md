# applyloop — SPEC

> It applied while I slept, then told me what I lack, from my own rejections.

The product: a local job-search agent that finds openings (whatshiring), prepares each application from your resume (resume intake, below) and your saved answers (answerbank), submits it in **your own Chrome** at a human pace (ratekeeper), and learns from the replies (ghosted). A local web UI shows everything as it happens and lets you pause, approve or auto-approve, add roles and resumes, and answer new questions.

## The hook (README opens with this)
A 30-second video of the UI: the pipeline filling up overnight, one application waiting for approval, a question answered once, and the "what you lack" panel, backed by real outcome numbers from the author's own search.

## Profile-agnostic, resume-agnostic
- **Any Chrome profile.** Config takes `user_data_dir` plus `profile_directory`, or `cdp_url` to attach to a Chrome you started yourself.
  - Since Chrome 136, automation can't attach to Chrome's *default* profile folder, so the default is a dedicated folder, `~/.applyloop/chrome`. You log into your sites once there; Chrome's password manager (with sync, if you choose) fills logins from then on.
  - applyloop never reads cookies, the password store or the keychain. It clicks into a login form and lets Chrome fill it; if Chrome doesn't, it pauses and asks you.
- **Any resume, any number of them.** Each resume variant is a JSON Resume file from resume intake with a label (e.g. `backend-v2`). Variants are chosen per job by fit, and every application records which one was sent, so ghosted can compare them.

## Must have (v1)
0. **Resume intake** (was a separate repo, atsview). Any resume becomes a reviewed JSON Resume file, and the user sees what a parser loses from it. Prior art: [OpenResume](https://github.com/xitanggg/open-resume)'s parser page (AGPL, so study only).

   1. **Inputs:**
      - DOCX: stdlib zip + XML, reading text boxes, tables and headers/footers separately so it can report where text lived
      - PDF: pdfplumber (character positions and a raw text stream, so layout problems can be measured)
      - Markdown, TXT, and JSON Resume (pass-through validation)
   2. **Findings**, each with the exact text as evidence:
      - reading-order problems: columns interleaved (lines alternating between two x-ranges in PDF layout mode, compared with raw mode)
      - letter-spaced words (`P y t h o n`)
      - icons or glyphs turned into private-use characters or `□`
      - contact details only in a header/footer or a text box
      - text inside images (the page has images but little text)
      - missing standard section headings (Experience, Education, Skills)
      - dates in formats parsers often miss
   3. **Structuring into JSON Resume:** rules for headings, dates, bullets, emails, phones and URLs; the local model (`LLM_BASE_URL`) is optional and only structures, never rewrites. Output includes `x-canon: {source, sha256, extractor, reviewed: false}`.
   4. **Review step:** `applyloop resume review resume.json` opens a local HTML diff of source text vs structured fields. The user marks it reviewed; other tools warn on unreviewed files.
   5. **Picture output:** `applyloop resume show resume.pdf --html out.html` renders the side-by-side view (the shareable image). It works with no model and no network.
   6. **Libraries:** [pdfplumber](https://github.com/jsvine/pdfplumber) (MIT) for PDF: character positions make column and letter-spacing detection measurable, not guessed. DOCX is read with the standard library (zip + XML).
   - No "ATS score": there is no single ATS, and a made-up score is what this project argues against.

1. **Pipeline stages,** each persisted in SQLite so the whole run can stop and resume at any point:
   `discover → rank → prepare → approve → submit → track`
2. **Discover and rank:** whatshiring, for the roles you list plus adjacent roles it suggests (shown separately until you accept them).
3. **Prepare:**
   - pick the resume variant with the best fit
   - answer the form's questions via answerbank; unknown ones go to the question queue
   - an optional drafted cover letter, marked as drafted
4. **Approve:**
   - manual by default: every prepared application waits in the approval queue with the filled form and a screenshot
   - **auto-approve** when every rule holds (all configurable):
     - fit score ≥ threshold
     - every answer comes from stored facts (no pending or drafted answers, unless drafted essays are explicitly allowed)
     - the company isn't on the block list and hasn't been applied to within N days
     - the daily application cap isn't reached
   - a global **kill switch** in the UI stops auto-approval immediately
5. **Submit:**
   - one label-driven extractor for Greenhouse, Lever, Ashby and plain forms; anything it can't answer with confidence goes to the questions queue or back to approval
   - screenshots before and after submit; a success check (confirmation page or message)
   - every action goes through ratekeeper
   - **dry-run mode** fills forms but never clicks submit
6. **Track:** writes the `applications` table; runs ghosted on a schedule; shows outcomes.
7. **Under target:** if the daily target isn't reached (not enough good matches), applyloop widens the search within bounds: adjacent roles you accepted, then a lower fit threshold down to a floor you set. It never goes below the floor, and it reports "only N good matches today" instead of padding.
8. **The UI** (Python stdlib `http.server`, one HTML file, live updates by server-sent events), bound to `127.0.0.1` with a per-session token:
   - **Pipeline:** live stage counts and an event log
   - **Approvals:** filled form preview, screenshot, edit, approve or reject, and the auto-approve toggle
   - **Questions:** new screening questions to answer once
   - **Roles and resumes:** add or remove roles, upload a resume (goes through resume intake, then review), pick defaults
   - **Budgets:** ratekeeper status per site, with pause and resume per site or for everything
   - **Outcomes:** ghosted's survival curve, rates by variant and role, and "what you lack"
   - **Controls:** start, pause, resume, stop, dry-run
9. **Models:** `LLM_BASE_URL` per task (`extract`, `draft`, `classify`), local by default.
10. **Dependencies:** the four sibling packages, Playwright, and pdfplumber (optional, for PDF resumes).
    - **As built:** no per-site adapters. One label-driven extractor covers the four form shapes found on real Greenhouse, Lever and Ashby pages (plain labels, custom dropdowns, question cards with radios, Yes/No buttons). Checked against a live Greenhouse form in dry-run mode: 9 fields filled, 8 questions sent to answerbank, nothing submitted.
    - A browser-use fallback for unfamiliar forms is deferred to v2: unknown fields go to the approval queue instead.

## Won't do (v1)
- LinkedIn Easy Apply or any site whose terms forbid automation (listed in the README, with the reason).
- CAPTCHA solving, proxy rotation or fingerprint spoofing.
- Reading Chrome's saved passwords or cookies.
- Unlimited volume: the default daily cap is 15. Raising it is the user's choice, and the README explains why low volume plus good fit beats spraying.

## Expectations → test cases
Fixtures: local copies of Greenhouse, Lever and Ashby application pages served by a test server; a fake local model; and fake job-board data. Browser tests run headless Chromium with a temporary profile.

| ID | Given | Then |
|---|---|---|
| E1 | A Greenhouse fixture form and a complete answer bank | Every field filled; dry-run stops before submit; screenshot saved |
| E2 | A form with a question not in the bank | The application goes to *Questions*; after answering in the UI, it continues |
| E3 | Auto-approve on; fit 0.82 ≥ 0.75; all answers stored | Submitted without a human; recorded as `mode=auto` |
| E4 | Auto-approve on, but one answer is drafted | Waits in *Approvals* (drafted answers not allowed) |
| E5 | Kill switch pressed during a run | No further auto-approvals; the in-flight submit finishes or aborts cleanly |
| E6 | The process is killed mid-pipeline | On restart, every stage resumes; nothing is submitted twice (idempotency key per job) |
| E7 | The site shows a CAPTCHA (fixture) | ratekeeper pauses the site; the UI shows "needs a human"; other sites continue |
| E8 | A login form appears and Chrome doesn't autofill | Pauses and asks the user; never types a password it read from anywhere |
| E9 | Only 4 matches above the threshold, target 10 | Widens to accepted adjacent roles and the floor; reports "only N good matches today" |
| E10 | UI request without the session token, or from a non-local origin | Rejected |
| E11 | Upload a new resume in the UI | Resume intake parses it; it's used only after it's marked reviewed |
| E12 | `cdp_url` given for a user-started Chrome | Attaches to it instead of launching one |
| E13 | A two-column resume fixture; one with contact details only in the page header | Resume intake reports "columns may be read out of order" and "contact details only in the page header", quoting the text |
| E14 | Resume structuring with a fake model | Any value not found in the source text is rejected; the same input gives identical JSON |

## Done when
E1–E12 pass; the author uses it for a real job search for at least two weeks; and the README opens with the demo video and real outcome numbers from ghosted.
