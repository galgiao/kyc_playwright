# Qichacha KYC Scraper API

FastAPI service that uses Playwright login storage to search Qichacha and extract company KYC data.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For local development, `--reload` is useful:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Binding to `127.0.0.1` only allows access from the server itself. Use `0.0.0.0` when the login UI or API must be opened from another machine, and make sure the cloud firewall or EC2 security group allows TCP `8000`.

## Linux Server Dependencies

Headless Chromium still needs Linux system libraries. If `/auth/session/start` fails with `Host system is missing dependencies to run browsers`, install the OS packages below.

Amazon Linux 2023:

```bash
sudo dnf install -y \
  atk at-spi2-atk at-spi2-core \
  cups-libs libdrm libX11 libXcomposite libXdamage libXext libXfixes libXrandr \
  mesa-libgbm libxcb libxkbcommon \
  pango cairo alsa-lib \
  nss nspr gtk3 expat
```

Amazon Linux 2:

```bash
sudo yum install -y \
  atk at-spi2-atk at-spi2-core \
  cups-libs libdrm libX11 libXcomposite libXdamage libXext libXfixes libXrandr \
  mesa-libgbm libxcb libxkbcommon \
  pango cairo alsa-lib \
  nss nspr gtk3 expat
```

Then verify:

```bash
ldd ~/.cache/ms-playwright/chromium-*/chrome-linux/chrome | grep "not found" || echo "browser deps ok"
```

Install Chinese fonts to avoid broken or blurry rendering in screenshots:

```bash
sudo dnf install -y fontconfig freetype dejavu-sans-fonts liberation-fonts
dnf search noto | grep -i cjk
sudo dnf install -y google-noto-sans-cjk-fonts
fc-cache -fv
fc-match "Noto Sans CJK SC"
```

If `google-noto-sans-cjk-fonts` is not available, use the CJK package name returned by `dnf search`, such as `google-noto-cjk-fonts` or `google-noto-sans-cjk-vf-fonts`.

## Run as a Systemd Service

Use `systemd` to keep the API running after SSH logout and restart it after server reboot.

Create an environment file:

```bash
sudo tee /etc/kyc-playwright.env >/dev/null <<'EOF'
APP_STORAGE_STATE_PATH=/home/ec2-user/kyc_playwright/data/qcc_storage_state.json
APP_USER_DATA_DIR=/home/ec2-user/kyc_playwright/data/qcc_user_data
APP_BROWSER_HEADLESS=true
APP_NAVIGATION_TIMEOUT_MS=45000
APP_EXTRACTION_TIMEOUT_MS=12000
EOF
```

Create the service unit:

```bash
sudo tee /etc/systemd/system/kyc-playwright.service >/dev/null <<'EOF'
[Unit]
Description=Qichacha KYC Playwright API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/home/ec2-user/kyc_playwright
EnvironmentFile=/etc/kyc-playwright.env
ExecStart=/home/ec2-user/kyc_playwright/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

Start and enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kyc-playwright
sudo systemctl status kyc-playwright
```

View logs:

```bash
sudo journalctl -u kyc-playwright -f
```

Restart after code changes:

```bash
cd /home/ec2-user/kyc_playwright
git pull
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
sudo systemctl restart kyc-playwright
```

If the project path or Linux user is different, update `User`, `Group`, `WorkingDirectory`, `ExecStart`, and `/etc/kyc-playwright.env`.

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
curl -X POST http://SERVER:8000/companies/kyc \
  -H 'Content-Type: application/json' \
  -d '{"company_name":"广大集团"}'
```

The response includes selected search result, detail URL, parsed basic fields, parsed qualification rows, and raw section snippets for troubleshooting selector drift.

Example response shape:

```json
{
  "query": "广大集团",
  "selected_company": {
    "name": "匹配到的企业名称",
    "url": "企查查详情页URL",
    "match_text": "搜索结果文本"
  },
  "detail_url": "实际打开的详情页URL",
  "basic_info": {
    "统一社会信用代码": "...",
    "法定代表人": "...",
    "注册资本": "...",
    "成立日期": "...",
    "经营状态": "...",
    "注册地址": "...",
    "经营范围": "..."
  },
  "qualification_info": {
    "items": [{"text": "资质/行政许可行文本"}],
    "summary": "解析到 N 行资质/许可文本",
    "text": "原始资质区块文本"
  },
  "raw_sections": {
    "title": "...",
    "工商信息": "...",
    "资质信息": "...",
    "行政许可": "..."
  }
}
```

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

## Troubleshooting

- `BrowserType.launch_persistent_context` reports missing dependencies: install the Linux server packages above.
- Login screenshot is blank or text is broken: install Chinese fonts and run `fc-cache -fv`.
- QR code is cut off: refresh the login UI screenshot; if needed, increase the Playwright viewport height in `app/qcc.py`.
- `TargetClosedError` during shutdown after pressing `Ctrl+C`: the browser context was already closing while the login UI was still polling. Restart the server normally.
- External browser cannot open the UI: run Uvicorn with `--host 0.0.0.0` and open the EC2 security group port.

Use only accounts and data access that you are authorized to use, and comply with Qichacha terms and applicable law.
