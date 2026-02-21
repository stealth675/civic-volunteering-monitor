from __future__ import annotations


def fetch_rendered_html(url: str, timeout_ms: int = 15000) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright ikke installert") from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=timeout_ms)
        page.wait_for_timeout(1200)
        html = page.content()
        browser.close()
    return html
