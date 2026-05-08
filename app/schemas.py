from typing import Any

from pydantic import BaseModel, Field


class LoginInitResponse(BaseModel):
    login_url: str
    message: str


class LoginCacheRequest(BaseModel):
    storage_state: dict[str, Any] = Field(
        ...,
        description="Playwright browser_context.storage_state() JSON.",
    )


class LoginCacheResponse(BaseModel):
    saved: bool
    storage_state_path: str


class LoginSessionResponse(BaseModel):
    started: bool
    login_url: str
    login_ui_url: str = "/auth/login-ui"
    message: str


class LoginSessionStatusResponse(BaseModel):
    active: bool
    url: str | None = None
    title: str | None = None


class LoginClickRequest(BaseModel):
    x: float = Field(..., ge=0)
    y: float = Field(..., ge=0)


class LoginTypeRequest(BaseModel):
    text: str


class LoginPressRequest(BaseModel):
    key: str = Field(..., min_length=1)


class LoginStatusResponse(BaseModel):
    logged_in: bool
    evidence: str | None = None


class CompanySearchRequest(BaseModel):
    company_name: str = Field(..., min_length=1)
    headless: bool | None = None


class CompanySearchHit(BaseModel):
    name: str
    url: str
    match_text: str | None = None


class CompanyKycResponse(BaseModel):
    query: str
    selected_company: CompanySearchHit | None
    detail_url: str | None
    basic_info: dict[str, str]
    qualification_info: dict[str, Any]
    raw_sections: dict[str, str]
