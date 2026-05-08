import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

LOGIN_URL = "https://www.qcc.com/user_login"
OUTPUT_PATH = Path("data/qcc_storage_state.json")


async def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1440, "height": 1000},
        )
        page = await context.new_page()
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print("请在打开的浏览器中完成企查查登录。完成后回到终端按 Enter 保存缓存。")
        await asyncio.to_thread(input)
        storage_state = await context.storage_state()
        OUTPUT_PATH.write_text(
            json.dumps(storage_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"已保存登录缓存: {OUTPUT_PATH}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
