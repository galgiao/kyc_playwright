from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from app.login_ui import LOGIN_UI_HTML

from app.config import get_settings
from app.qcc import QccLoginSession, QccScraper
from app.schemas import (
    CompanyKycResponse,
    CompanySearchRequest,
    LoginClickRequest,
    LoginCacheRequest,
    LoginCacheResponse,
    LoginInitResponse,
    LoginPressRequest,
    LoginSessionResponse,
    LoginSessionStatusResponse,
    LoginStatusResponse,
    LoginTypeRequest,
)

app = FastAPI(
    title="Qichacha KYC Scraper API",
    version="0.1.0",
    description="Use Playwright login storage to search Qichacha and extract KYC fields.",
)


@app.on_event("shutdown")
async def shutdown_login_session() -> None:
    session = getattr(app.state, "qcc_login_session", None)
    if session:
        await session.close()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/cache", response_model=LoginCacheResponse)
async def save_login_cache(payload: LoginCacheRequest) -> LoginCacheResponse:
    settings = get_settings()
    path = await QccScraper(settings).save_storage_state(payload.storage_state)
    return LoginCacheResponse(saved=True, storage_state_path=str(path))


@app.get("/auth/init", response_model=LoginInitResponse)
async def init_login() -> LoginInitResponse:
    settings = get_settings()
    return LoginInitResponse(
        login_url="/auth/login-ui",
        message=(
            "请打开 /auth/login-ui，使用服务器后台 headless Chromium 完成企查查登录，"
            "然后点击页面上的保存登录态。"
        ),
    )


@app.get("/auth/login-ui", response_class=HTMLResponse)
async def login_ui() -> str:
    return LOGIN_UI_HTML


@app.post("/auth/session/start", response_model=LoginSessionResponse)
async def start_login_session() -> LoginSessionResponse:
    settings = get_settings()
    session = getattr(app.state, "qcc_login_session", None)
    if session is None:
        session = QccLoginSession(settings)
        app.state.qcc_login_session = session
    await session.start()
    return LoginSessionResponse(
        started=True,
        login_url=settings.qcc_login_url,
        login_ui_url="/auth/login-ui",
        message="已启动服务器后台 headless Chromium。请在 /auth/login-ui 完成登录并保存登录缓存。",
    )


@app.get("/auth/session/status", response_model=LoginSessionStatusResponse)
async def login_session_status() -> LoginSessionStatusResponse:
    session = getattr(app.state, "qcc_login_session", None)
    if session is None:
        return LoginSessionStatusResponse(active=False)
    return LoginSessionStatusResponse(**await session.status())


@app.get("/auth/session/screenshot")
async def login_session_screenshot() -> Response:
    session = getattr(app.state, "qcc_login_session", None)
    if session is None:
        session = QccLoginSession(get_settings())
        app.state.qcc_login_session = session
        await session.start()
    return Response(content=await session.screenshot(), media_type="image/png")


@app.post("/auth/session/click")
async def login_session_click(payload: LoginClickRequest) -> dict[str, bool]:
    session = getattr(app.state, "qcc_login_session", None)
    if session is None:
        session = QccLoginSession(get_settings())
        app.state.qcc_login_session = session
        await session.start()
    await session.click(payload.x, payload.y)
    return {"ok": True}


@app.post("/auth/session/type")
async def login_session_type(payload: LoginTypeRequest) -> dict[str, bool]:
    session = getattr(app.state, "qcc_login_session", None)
    if session is None:
        session = QccLoginSession(get_settings())
        app.state.qcc_login_session = session
        await session.start()
    await session.type_text(payload.text)
    return {"ok": True}


@app.post("/auth/session/press")
async def login_session_press(payload: LoginPressRequest) -> dict[str, bool]:
    session = getattr(app.state, "qcc_login_session", None)
    if session is None:
        session = QccLoginSession(get_settings())
        app.state.qcc_login_session = session
        await session.start()
    await session.press(payload.key)
    return {"ok": True}


@app.post("/auth/session/save", response_model=LoginCacheResponse)
async def save_login_session() -> LoginCacheResponse:
    session = getattr(app.state, "qcc_login_session", None)
    if session is None:
        session = QccLoginSession(get_settings())
        app.state.qcc_login_session = session
    path = await session.save_and_close()
    return LoginCacheResponse(saved=True, storage_state_path=str(path))


@app.get("/auth/status", response_model=LoginStatusResponse)
async def login_status() -> LoginStatusResponse:
    logged_in, evidence = await QccScraper(get_settings()).check_login()
    return LoginStatusResponse(logged_in=logged_in, evidence=evidence)


@app.post("/companies/kyc", response_model=CompanyKycResponse)
async def company_kyc(payload: CompanySearchRequest) -> CompanyKycResponse:
    result = await QccScraper(get_settings()).fetch_company_kyc(
        payload.company_name.strip(),
        headless=payload.headless,
    )
    return CompanyKycResponse(**result)
