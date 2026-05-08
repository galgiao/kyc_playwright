# Project Positioning and Runtime Shape

FastAPI service for Qichacha KYC scraping. Runtime loads a Playwright login `storage_state` file, searches Qichacha, opens the selected company detail page, and extracts basic company fields plus qualification or licensing text. Login initialization works on no-GUI Linux servers through a FastAPI web page that remotely controls a headless Playwright browser.

# Directory Responsibilities

- `app/main.py`: FastAPI app, route definitions, request/response wiring.
- `app/qcc.py`: Playwright browser lifecycle, Qichacha navigation, login checks, scraping, parser helpers.
- `app/login_ui.py`: HTML page for no-GUI server login interaction with the headless browser.
- `app/config.py`: environment-backed settings and filesystem paths.
- `app/schemas.py`: Pydantic API models.
- `scripts/export_qcc_storage_state.py`: headed Playwright helper for manual Qichacha login and local storage-state export.
- `requirements.txt`: Python runtime dependencies.
- `data/`: ignored local runtime cache for login state and browser profile data.

# Runtime Entrypoints

- API server: `uvicorn app.main:app --reload`.
- Health check: `GET /health`.
- Login bootstrap: `GET /auth/init`.
- Server-side headless login start: `POST /auth/session/start`.
- Web login UI: `GET /auth/login-ui`.
- Server-side login status: `GET /auth/session/status`.
- Server-side login screenshot: `GET /auth/session/screenshot`.
- Server-side login click/type/press: `POST /auth/session/click`, `POST /auth/session/type`, `POST /auth/session/press`.
- Server-side login save: `POST /auth/session/save`.
- Login cache save: `POST /auth/cache`.
- Login status check: `GET /auth/status`.
- Company KYC scrape: `POST /companies/kyc`.

# Feature to Code Control Map

- Login cache ingestion is controlled by `save_login_cache()` in `app/main.py` and `QccScraper.save_storage_state()` in `app/qcc.py`.
- Server-side manual login is controlled by login session routes in `app/main.py`, the HTML in `app/login_ui.py`, and `QccLoginSession` in `app/qcc.py`.
- Login status validation is controlled by `login_status()` in `app/main.py` and `QccScraper.check_login()` in `app/qcc.py`.
- Company search and detail scraping are controlled by `company_kyc()` in `app/main.py` and `QccScraper.fetch_company_kyc()` in `app/qcc.py`.
- Basic information parsing lives in `QccScraper._extract_basic_info()` and `_parse_label_values()`.
- Qualification information parsing lives in `QccScraper._extract_qualification_info()` and `_parse_rows()`.

# Config and Env Locations

- Settings class: `app/config.py`.
- Optional `.env` prefix: `APP_`.
- Login storage file default: `data/qcc_storage_state.json`.
- Browser profile directory default: `data/qcc_user_data`.
- Headless default: `APP_BROWSER_HEADLESS=true`.

# Database/Migration Entry

No database or migrations exist. Runtime state is local JSON/cache under `data/`.

# Fast Troubleshooting Index

- `401` from `/companies/kyc`: refresh Playwright login cache with `POST /auth/cache`.
- Empty `basic_info`: inspect `raw_sections` in the response; Qichacha selectors may have changed.
- Browser launch errors: run `playwright install chromium` in the active Python environment.
- Timeout errors: raise `APP_NAVIGATION_TIMEOUT_MS` or retry with `"headless": false`.

# Maintenance Rules

Keep API routes, settings names, and scraper responsibilities reflected here when files change. Keep Qichacha-specific selectors isolated in `app/qcc.py`.
