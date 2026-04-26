# Code Quality & Security Review — Exercise Tracker

Strict review of the existing codebase. No functionality changes — only quality, security, and maintainability improvements.

---

## 🔴 Critical

### 1. XSS vulnerabilities in client-side HTML building
`templates/index.html:325-346, 1129, 1167, 1291`

The `lookupRecent()` function and chart card creation inject unsanitized data (exercise names, notes) directly into `innerHTML`. A malicious note like `<img src=x onerror=alert(1)>` will execute.

**Fix:** Create an `escapeHtml()` utility and use it everywhere user/DB data is interpolated into HTML strings.

### 2. Weak default SECRET_KEY
`exercise_tracker/config.py:7`

Falls back to `"dev-secret"` if env var not set. Allows session forgery if deployed without the variable.

**Fix:** Raise an error on startup if `SECRET_KEY` is not set, rather than using a guessable default.

### 3. `debug=True` hardcoded in app.py
`app.py:8`

Exposes the Werkzeug debugger (remote code execution risk) if this entrypoint is used in production.

**Fix:** Gate on env var: `debug=os.environ.get("FLASK_DEBUG", "").lower() == "true"`

---

## 🟠 High

### 4. Database connection leaks on error paths
`exercise_tracker/db.py:59-144`, `stats.py`, `plan.py`, `parsing.py`, `api_routes.py`, `telegram_routes.py`

Every module manually calls `conn.close()` at the end of the happy path only. Any exception before that line leaks a connection.

**Fix:** Create a context manager (`with get_db() as conn:`) or use `try/finally` consistently. Alternatively, use Flask's `g` object + `teardown_appcontext` for request-scoped connections.

### 5. Massive inline JS/CSS duplication across templates
`templates/index.html` (~680 lines JS), `templates/stats.html` (~570 lines JS)

Heatmap, timeline, density, Chart.js config, and category color maps are copy-pasted across templates. Changes must be made in multiple places (already caused bugs).

**Fix:** Extract to shared static files:
- `static/js/charts.js` — Chart.js helpers, category colors, progress chart rendering
- `static/js/heatmap.js` — heatmap + timeline rendering
- `static/css/main.css` — shared styles, category badge classes

### 6. Transaction handling without rollback protection
`exercise_tracker/routes/telegram_routes.py:414-426, 458-479`

Autocommit is disabled but there's no `try/except` to rollback on failure. An exception leaves the connection in an open transaction.

**Fix:** Wrap in `try/except/finally` with rollback on exception.

---

## 🟡 Medium

### 7. Missing security headers
`exercise_tracker/__init__.py`

No CSP, X-Frame-Options, HSTS, or other security headers are set.

**Fix:** Add a `@app.after_request` handler to set security headers, or add Flask-Talisman.

### 8. Inline event handlers prevent CSP
`templates/index.html:182, 302`, `templates/mobile.html:100, 144`

`onchange=`, `onkeydown=` in HTML attributes prevent using `script-src` CSP without `unsafe-inline`.

**Fix:** Move to `addEventListener` in JS.

### 9. `|safe` filter on narrative HTML
`templates/index.html:466`, `templates/stats.html:195`

`{{ m.narrative|safe }}` bypasses Jinja2 auto-escaping. Exercise names from the DB are interpolated into these narratives server-side without escaping.

**Fix:** Use `markupsafe.escape()` on exercise names when building narrative strings in `stats.py`.

### 10. No input validation on exercise codes in API routes
`exercise_tracker/routes/api_routes.py:40-61, 95-129`

Codes from user input are passed to DB queries without checking they exist in the exercises table first.

**Fix:** Validate against known codes before querying.

### 11. Telegram code lookups not validated against valid_codes
`exercise_tracker/routes/telegram_routes.py:321, 379`

`/recent` and `/notes` commands normalize the code but don't check `if code not in valid_codes` before querying.

**Fix:** Add explicit check after `normalize_code()`.

### 12. Unpinned dependency upper bounds
`pyproject.toml:5-10`

`flask>=3.0` will silently upgrade to 4.x. Same for all other deps.

**Fix:** Add upper bounds: `flask>=3.0,<4.0` etc.

### 13. Missing `.gitignore` entries
`.gitignore`

Missing: `*.egg-info/`, `.pytest_cache/`, `*.log`, `.DS_Store`, `.idea/`, `.vscode/`, `dist/`, `build/`.

**Fix:** Expand with standard Python gitignore patterns.

### 14. Accessibility: missing `lang` attribute and form labels
All templates

`<html>` missing `lang="en"`. Several inputs missing `<label>` or `aria-label`.

**Fix:** Add `lang="en"` to all `<html>` tags. Add labels to form inputs.

---

## 🟢 Low

### 15. Hardcoded DORMANT_DAYS
`exercise_tracker/plan.py:9`

Could be made configurable via env var with 35 as default.

### 16. Hardcoded color values defined in multiple places
All templates

Category colors defined in CSS, then redefined in JS `catColors` objects.

**Fix:** Use CSS custom properties and read them from JS, or generate from a single source.

### 17. Data export files committed to git
`data/data_export.txt`, `data/notes_export.txt`

The sync-data workflow commits exported data daily, growing the repo indefinitely.

**Fix:** Store exports outside git (cloud storage, DB backup) or add to `.gitignore`.

---

## Suggested priority order

1. **SECRET_KEY + debug=True** — trivial fixes, high impact
2. **XSS escaping** — add `escapeHtml()` helper, apply everywhere
3. **DB connection management** — context manager or teardown handler
4. **Extract shared JS/CSS** — biggest maintainability win
5. **Security headers** — `@app.after_request`
6. **Everything else** — medium/low items
