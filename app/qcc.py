import json
import re
from asyncio import Lock
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

from fastapi import HTTPException
from playwright.async_api import (
    BrowserContext,
    Page,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from app.config import Settings
from app.schemas import CompanySearchHit


class QccLoginSession:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.playwright: Any | None = None
        self.context: BrowserContext | None = None
        self._lock = Lock()

    async def start(self) -> None:
        async with self._lock:
            if self.context:
                return
            self.settings.user_data_dir.mkdir(parents=True, exist_ok=True)
            self.playwright = await async_playwright().start()
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.settings.user_data_dir),
                headless=True,
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                viewport={"width": 1440, "height": 1000},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await self.page()
            await page.goto(self.settings.qcc_login_url, wait_until="domcontentloaded")

    async def page(self) -> Page:
        if not self.context:
            raise HTTPException(status_code=409, detail="尚未启动登录会话，请先调用 /auth/session/start")
        try:
            open_pages = [page for page in self.context.pages if not page.is_closed()]
            return open_pages[-1] if open_pages else await self.context.new_page()
        except PlaywrightError as exc:
            await self._mark_closed()
            raise HTTPException(status_code=409, detail="登录浏览器会话已关闭，请重新启动") from exc

    async def status(self) -> dict[str, Any]:
        if not self.context:
            return {"active": False, "url": None, "title": None}
        try:
            page = await self.page()
            return {"active": True, "url": page.url, "title": await page.title()}
        except HTTPException:
            return {"active": False, "url": None, "title": None}
        except PlaywrightError:
            await self._mark_closed()
            return {"active": False, "url": None, "title": None}

    async def screenshot(self) -> bytes:
        async with self._lock:
            page = await self.page()
            await page.wait_for_load_state("domcontentloaded")
            return await page.screenshot(type="png", full_page=False)

    async def click(self, x: float, y: float) -> None:
        async with self._lock:
            page = await self.page()
            await page.mouse.click(x, y)

    async def type_text(self, text: str) -> None:
        async with self._lock:
            page = await self.page()
            await page.keyboard.type(text, delay=25)

    async def press(self, key: str) -> None:
        async with self._lock:
            page = await self.page()
            await page.keyboard.press(key)

    async def save_and_close(self) -> Path:
        async with self._lock:
            if not self.context or not self.playwright:
                raise HTTPException(status_code=409, detail="尚未启动登录会话，请先调用 /auth/session/start")
            path = self.settings.storage_state_path
            path.parent.mkdir(parents=True, exist_ok=True)
            await self.context.storage_state(path=str(path))
            await self._close_unlocked()
            return path

    async def close(self) -> None:
        async with self._lock:
            await self._close_unlocked()

    async def _close_unlocked(self) -> None:
        if self.context:
            try:
                await self.context.close()
            except (PlaywrightError, RuntimeError):
                pass
            self.context = None
        if self.playwright:
            try:
                await self.playwright.stop()
            except (PlaywrightError, RuntimeError):
                pass
            self.playwright = None

    async def _mark_closed(self) -> None:
        self.context = None
        if self.playwright:
            try:
                await self.playwright.stop()
            except (PlaywrightError, RuntimeError):
                pass
            self.playwright = None


class QccScraper:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def save_storage_state(self, storage_state: dict[str, Any]) -> Path:
        self._validate_storage_state(storage_state)
        path = self.settings.storage_state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(storage_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    async def check_login(self, headless: bool | None = None) -> tuple[bool, str | None]:
        async with self._managed_context(headless=headless) as context:
            page = await context.new_page()
            await self._goto(page, self.settings.qcc_base_url)
            body_text = await self._body_text(page)
            if any(token in body_text for token in ("退出", "我的企业", "会员中心")):
                return True, "页面出现已登录用户入口"
            if any(token in body_text for token in ("登录", "注册", "手机验证码登录")):
                return False, "页面仍出现登录入口"
            return False, "未找到稳定的登录态标识"

    async def fetch_company_kyc(
        self,
        company_name: str,
        headless: bool | None = None,
    ) -> dict[str, Any]:
        async with self._managed_context(headless=headless) as context:
            page = await context.new_page()
            search_url = f"{self.settings.qcc_search_url}?key={quote(company_name)}"
            await self._goto(page, search_url)
            await self._ensure_not_login_page(page)
            await self._settle(page)

            hit = await self._first_company_hit(page, company_name)
            if not hit:
                return {
                    "query": company_name,
                    "selected_company": None,
                    "detail_url": None,
                    "basic_info": {},
                    "qualification_info": {},
                    "raw_sections": {"search_page": await self._body_text(page)},
                }

            detail_page = await self._open_detail_page(context, page, hit.url)
            await self._ensure_not_login_page(detail_page)
            await self._settle(detail_page)

            basic_info = await self._extract_basic_info(detail_page)
            qualification_info = await self._extract_qualification_info(detail_page)
            raw_sections = await self._extract_raw_sections(detail_page)

            return {
                "query": company_name,
                "selected_company": hit.model_dump(),
                "detail_url": detail_page.url,
                "basic_info": basic_info,
                "qualification_info": qualification_info,
                "raw_sections": raw_sections,
            }

    async def fetch_company_food_safety(
        self,
        company_name: str,
        headless: bool | None = None,
    ) -> dict[str, Any]:
        async with self._managed_context(headless=headless) as context:
            page = await context.new_page()
            search_url = f"{self.settings.qcc_search_url}?key={quote(company_name)}"
            await self._goto(page, search_url)
            await self._ensure_not_login_page(page)
            await self._settle(page)

            hit = await self._first_company_hit(page, company_name)
            if not hit:
                return {
                    "query": company_name,
                    "selected_company": None,
                    "detail_url": None,
                    "food_safety_info": {"items": [], "summary": "未找到企业搜索结果"},
                    "raw_sections": {"search_page": await self._body_text(page)},
                }

            detail_page = await self._open_detail_page(context, page, hit.url)
            await self._ensure_not_login_page(detail_page)
            await self._settle(detail_page)

            food_safety_info = await self._extract_food_safety_info(detail_page)
            raw_sections = await self._extract_food_safety_raw_sections(detail_page)

            return {
                "query": company_name,
                "selected_company": hit.model_dump(),
                "detail_url": detail_page.url,
                "food_safety_info": food_safety_info,
                "raw_sections": raw_sections,
            }

    async def _open_detail_page(
        self,
        context: BrowserContext,
        page: Page,
        url: str,
    ) -> Page:
        if url.startswith("javascript:"):
            raise HTTPException(status_code=502, detail="搜索结果链接不可访问")

        absolute_url = urljoin(self.settings.qcc_base_url, url)
        existing_pages = set(context.pages)
        try:
            async with context.expect_page(timeout=5000) as new_page_info:
                await page.evaluate("(href) => window.open(href, '_blank')", absolute_url)
            detail_page = await new_page_info.value
        except PlaywrightTimeoutError:
            await page.goto(absolute_url, wait_until="domcontentloaded")
            detail_page = page

        if detail_page not in existing_pages:
            await detail_page.wait_for_load_state("domcontentloaded")
        return detail_page

    async def _first_company_hit(
        self,
        page: Page,
        company_name: str,
    ) -> CompanySearchHit | None:
        link_candidates = page.locator(
            "a[href*='/firm/'], a[href*='/company/'], a[href*='/web/firm/']"
        )
        count = await link_candidates.count()
        best: CompanySearchHit | None = None
        for index in range(min(count, 20)):
            link = link_candidates.nth(index)
            text = self._normalize(await link.inner_text(timeout=3000))
            href = await link.get_attribute("href")
            if not href or not text:
                continue
            if company_name in text or best is None:
                best = CompanySearchHit(name=self._first_line(text), url=href, match_text=text)
                if company_name in text:
                    return best
        return best

    async def _extract_basic_info(self, page: Page) -> dict[str, str]:
        selectors = [
            "#cominfo",
            "section:has-text('工商信息')",
            "div:has-text('工商信息') table",
            "table:has-text('统一社会信用代码')",
        ]
        text = await self._first_visible_text(page, selectors)
        if not text:
            text = await self._body_text(page)
        return self._parse_label_values(
            text,
            labels=[
                "统一社会信用代码",
                "法定代表人",
                "注册资本",
                "成立日期",
                "企业类型",
                "经营状态",
                "注册地址",
                "经营范围",
                "营业期限",
                "登记机关",
                "核准日期",
                "所属行业",
                "纳税人识别号",
                "组织机构代码",
                "工商注册号",
            ],
        )

    async def _extract_qualification_info(self, page: Page) -> dict[str, Any]:
        await self._click_tab_if_present(page, ["资质", "行政许可", "证书", "许可"])
        text = await self._first_visible_text(
            page,
            [
                "section:has-text('资质')",
                "section:has-text('行政许可')",
                "div:has-text('资质') table",
                "div:has-text('行政许可') table",
                "table:has-text('许可证')",
                "table:has-text('资质')",
            ],
        )
        if not text:
            return {"items": [], "summary": "未找到资质或行政许可区块"}

        rows = self._parse_rows(text)
        return {
            "items": rows,
            "summary": f"解析到 {len(rows)} 行资质/许可文本",
            "text": text,
        }

    async def _extract_food_safety_info(self, page: Page) -> dict[str, Any]:
        labels = [
            "食品安全",
            "食品经营许可",
            "食品生产许可",
            "食品许可证",
            "食品相关",
            "抽查检查",
            "监督检查",
            "行政处罚",
            "产品质量",
        ]
        await self._click_tab_if_present(page, labels)
        text = await self._first_visible_text(
            page,
            [
                "section:has-text('食品安全')",
                "section:has-text('食品经营许可')",
                "section:has-text('食品生产许可')",
                "div:has-text('食品安全') table",
                "div:has-text('食品经营许可') table",
                "div:has-text('食品生产许可') table",
                "table:has-text('食品经营许可证')",
                "table:has-text('食品生产许可证')",
                "section:has-text('抽查检查')",
                "section:has-text('监督检查')",
                "div:has-text('抽查检查') table",
                "div:has-text('监督检查') table",
                "section:has-text('行政处罚')",
                "div:has-text('行政处罚') table",
            ],
        )
        if not text:
            body = await self._body_text(page)
            snippets = {
                label: self._slice_around(body, label)
                for label in labels
                if self._slice_around(body, label)
            }
            if not snippets:
                return {"items": [], "summary": "未找到食品安全相关区块", "snippets": {}}
            text = "\n".join(snippets.values())

        rows = self._parse_rows(text, ignored_headers=set(labels))
        fields = self._parse_label_values(
            text,
            labels=[
                "许可证编号",
                "食品经营许可证",
                "食品生产许可证",
                "许可编号",
                "许可机关",
                "发证机关",
                "有效期至",
                "有效期限",
                "许可内容",
                "检查结果",
                "检查机关",
                "处罚决定书文号",
                "处罚机关",
            ],
        )
        return {
            "items": rows,
            "fields": fields,
            "summary": f"解析到 {len(rows)} 行食品安全相关文本",
            "text": text,
        }

    async def _extract_raw_sections(self, page: Page) -> dict[str, str]:
        body = await self._body_text(page)
        return {
            "title": await page.title(),
            "工商信息": self._slice_around(body, "工商信息"),
            "资质信息": self._slice_around(body, "资质"),
            "行政许可": self._slice_around(body, "行政许可"),
        }

    async def _extract_food_safety_raw_sections(self, page: Page) -> dict[str, str]:
        body = await self._body_text(page)
        return {
            "title": await page.title(),
            "食品安全": self._slice_around(body, "食品安全"),
            "食品经营许可": self._slice_around(body, "食品经营许可"),
            "食品生产许可": self._slice_around(body, "食品生产许可"),
            "抽查检查": self._slice_around(body, "抽查检查"),
            "监督检查": self._slice_around(body, "监督检查"),
            "行政处罚": self._slice_around(body, "行政处罚"),
            "产品质量": self._slice_around(body, "产品质量"),
        }

    async def _click_tab_if_present(self, page: Page, labels: list[str]) -> None:
        for label in labels:
            locator = page.get_by_text(label, exact=False).first
            try:
                if await locator.count() and await locator.is_visible(timeout=1000):
                    await locator.click(timeout=3000)
                    await self._settle(page)
                    return
            except PlaywrightTimeoutError:
                continue

    async def _first_visible_text(self, page: Page, selectors: list[str]) -> str:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() and await locator.is_visible(timeout=1500):
                    return self._normalize(await locator.inner_text(timeout=3000))
            except PlaywrightTimeoutError:
                continue
        return ""

    def _managed_context(self, headless: bool | None = None):
        settings = self.settings

        class ContextManager:
            async def __aenter__(self_inner) -> BrowserContext:
                self_inner.playwright = await async_playwright().start()
                self_inner.browser = await self_inner.playwright.chromium.launch(
                    headless=settings.browser_headless if headless is None else headless
                )
                kwargs: dict[str, Any] = {
                    "locale": "zh-CN",
                    "timezone_id": "Asia/Shanghai",
                    "viewport": {"width": 1440, "height": 1000},
                    "user_agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                }
                if settings.storage_state_path.exists():
                    kwargs["storage_state"] = str(settings.storage_state_path)
                self_inner.context = await self_inner.browser.new_context(**kwargs)
                self_inner.context.set_default_timeout(settings.extraction_timeout_ms)
                return self_inner.context

            async def __aexit__(self_inner, exc_type, exc, tb) -> None:
                await self_inner.context.close()
                await self_inner.browser.close()
                await self_inner.playwright.stop()

        return ContextManager()

    async def _goto(self, page: Page, url: str) -> None:
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.settings.navigation_timeout_ms,
            )
        except PlaywrightTimeoutError as exc:
            raise HTTPException(status_code=504, detail=f"页面加载超时: {url}") from exc

    async def _settle(self, page: Page) -> None:
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            pass

    async def _ensure_not_login_page(self, page: Page) -> None:
        body_text = await self._body_text(page)
        if "手机验证码登录" in body_text or "微信扫码登录" in body_text:
            raise HTTPException(
                status_code=401,
                detail="企查查登录态无效，请重新提交 Playwright storage_state 登录缓存",
            )

    async def _body_text(self, page: Page) -> str:
        try:
            return self._normalize(await page.locator("body").inner_text(timeout=5000))
        except PlaywrightTimeoutError:
            return ""

    def _validate_storage_state(self, storage_state: dict[str, Any]) -> None:
        cookies = storage_state.get("cookies")
        origins = storage_state.get("origins")
        if not isinstance(cookies, list) or origins is None:
            raise HTTPException(
                status_code=422,
                detail="storage_state 必须包含 Playwright cookies 和 origins 字段",
            )

    def _parse_label_values(self, text: str, labels: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        escaped = "|".join(re.escape(label) for label in labels)
        for label in labels:
            pattern = rf"{re.escape(label)}\s*[:：]?\s*(.*?)(?=\s*(?:{escaped})\s*[:：]?|$)"
            match = re.search(pattern, text, flags=re.S)
            if match:
                value = self._normalize(match.group(1))
                if value:
                    result[label] = value
        return result

    def _parse_rows(self, text: str, ignored_headers: set[str] | None = None) -> list[dict[str, str]]:
        ignored = ignored_headers or {"资质", "行政许可", "证书"}
        lines = [line for line in text.splitlines() if line.strip()]
        rows: list[dict[str, str]] = []
        for line in lines:
            normalized = self._normalize(line)
            if normalized and normalized not in ignored:
                rows.append({"text": normalized})
        return rows

    def _slice_around(self, text: str, token: str, radius: int = 1200) -> str:
        index = text.find(token)
        if index < 0:
            return ""
        return text[max(0, index - 200) : index + radius]

    def _normalize(self, text: str) -> str:
        return re.sub(r"[ \t\r\f\v]+", " ", text).strip()

    def _first_line(self, text: str) -> str:
        return text.splitlines()[0].strip()
