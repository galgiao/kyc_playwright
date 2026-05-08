# Qichacha KYC Scraper API

FastAPI service that uses Playwright login storage to search Qichacha and extract company KYC data.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

## Login Cache Flow

Option A, no-GUI Linux server:

1. Open `http://SERVER:8000/auth/login-ui`.
2. Click `启动`.
3. Use the page screenshot to scan QR codes, click fields, type text, and submit the Qichacha login.
4. Click `保存登录态`.
5. Verify with `GET /auth/status`.

The server runs Chromium in headless mode and publishes this web interaction page through FastAPI. It does not require X11, VNC, or a desktop session.

Option B, API-only flow for the same web login session:

1. Call `POST /auth/session/start`.
2. Interact through `GET /auth/session/screenshot`, `POST /auth/session/click`, `POST /auth/session/type`, and `POST /auth/session/press`.
3. Call `POST /auth/session/save`.
4. Verify with `GET /auth/status`.

Option C, send cache from your own Playwright client:

1. Open `GET /auth/init` and copy `login_url`.
2. Log in to Qichacha in a Playwright browser.
3. Send the logged-in `browser_context.storage_state()` JSON to `POST /auth/cache`.
4. Verify with `GET /auth/status`.

Local helper:

```bash
python scripts/export_qcc_storage_state.py
```

After logging in, this writes `data/qcc_storage_state.json`, which is the same file used by the API. If you already have a Playwright client, you can still submit its `storage_state` JSON to `/auth/cache`.

Example cache request:

```bash
curl -X POST http://127.0.0.1:8000/auth/cache \
  -H 'Content-Type: application/json' \
  -d '{"storage_state":{"cookies":[],"origins":[]}}'
```

## Scrape Company KYC

```bash
curl -X POST http://127.0.0.1:8000/companies/kyc \
  -H 'Content-Type: application/json' \
  -d '{"company_name":"腾讯科技（深圳）有限公司"}'
```

The response includes selected search result, detail URL, parsed basic fields, parsed qualification rows, and raw section snippets for troubleshooting selector drift.

## Environment

Settings are controlled by `APP_` variables or `.env`.

- `APP_QCC_BASE_URL`
- `APP_QCC_LOGIN_URL`
- `APP_QCC_SEARCH_URL`
- `APP_STORAGE_STATE_PATH`
- `APP_USER_DATA_DIR`
- `APP_BROWSER_HEADLESS`
- `APP_NAVIGATION_TIMEOUT_MS`
- `APP_EXTRACTION_TIMEOUT_MS`

Use only accounts and data access that you are authorized to use, and comply with Qichacha terms and applicable law.
