import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Optional

from playwright.async_api import Page, Browser

from scoring import Event, clean_text, detect_language

logger = logging.getLogger(__name__)


STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});
Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32',
});
"""

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]


def random_delay(min_s: float = 2.0, max_s: float = 5.0) -> float:
    return random.uniform(min_s, max_s)


async def create_context(browser: Browser):
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={
            "width": random.randint(1280, 1440),
            "height": random.randint(800, 900),
        },
        locale="en-US",
        timezone_id="Europe/Paris",
    )
    await context.add_init_script(STEALTH_SCRIPT)
    return context


async def try_click_cookie_banner(page: Page):
    patterns = [
        "button:has-text('Accept')",
        "button:has-text('Accepter')",
        "button:has-text('Accept all')",
        "button:has-text('Tout accepter')",
        "button:has-text('Got it')",
        "button:has-text('OK')",
        '[aria-label*="cookie"] button',
        '[class*="cookie"] button',
    ]
    for pattern in patterns:
        try:
            btn = await page.query_selector(pattern)
            if btn:
                await btn.click()
                await asyncio.sleep(0.5)
                return
        except Exception:
            logger.debug("Cookie banner selector failed: %s", pattern)
            continue


async def safe_goto(page: Page, url: str, timeout: int = 30000) -> bool:
    for attempt in range(2):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            await asyncio.sleep(random_delay(2, 4))
            await try_click_cookie_banner(page)
            await page.wait_for_load_state("networkidle", timeout=10000)
            return True
        except Exception as e:
            logger.warning(f"Navigation failed: {url[:60]}... ({e})")
            if attempt == 0:
                delay = 2 ** (attempt + 2)
                logger.info(f"Retrying in {delay}s...")
                await asyncio.sleep(delay)
    return False


PLATFORM_SELECTORS: dict[str, dict[str, list[str]]] = {
    "Meetup": {
        "title": ["h1"],
        "description": [
            '[data-testid="event-description"]',
            '[class*="description"]',
            '[itemprop="description"]',
            "main",
            "article",
        ],
        "date": [
            "time",
            '[data-testid="event-time"]',
            '[class*="dateTime"]',
            '[class*="date"]',
        ],
        "venue": [
            '[data-testid="venue"]',
            '[class*="venue"]',
            '[class*="location"]',
        ],
        "organizer": [
            '[data-testid="group-name"]',
            '[class*="groupName"]',
            '[class*="organizer"]',
            "a[href*='/groups/']",
        ],
        "price": [
            '[class*="price"]',
            '[class*="ticket"]',
        ],
    },
    "Luma": {
        "title": ["h1"],
        "description": [
            '[class*="description"]',
            '[class*="content"]',
            "main",
            "article",
        ],
        "date": [
            "time",
            '[class*="date"]',
            '[class*="time"]',
            '[class*="schedule"]',
        ],
        "venue": [
            '[class*="location"]',
            '[class*="venue"]',
            '[class*="address"]',
        ],
        "organizer": [
            '[class*="host"]',
            '[class*="organizer"]',
            "a[href*='/calendar/']",
        ],
        "price": [
            '[class*="price"]',
            '[class*="ticket"]',
        ],
    },
}


async def _extract_field(
    page: Page,
    selectors: list[str],
    max_len: int = 0,
    min_len: int = 0,
) -> str:
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = clean_text(await el.inner_text(), max_len)
                if len(text) >= min_len:
                    return text
        except Exception:
            continue
    return ""


async def extract_event(page: Page, url: str, platform: str) -> Optional[Event]:
    event: Event = {
        "title": "",
        "date": "",
        "time": "",
        "platform": platform,
        "link": url,
        "venue": "",
        "organizer": "",
        "description": "",
        "price": "",
        "format": "",
        "language": "",
        "topic_tags": "",
        "score": 0,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    ok = await safe_goto(page, url, timeout=20000)
    if not ok:
        return None

    try:
        await page.wait_for_selector("h1", timeout=8000)
    except Exception:
        logger.debug("No h1 found on page: %s", url[:80])
        pass

    body = page
    selectors = PLATFORM_SELECTORS[platform]

    title = await _extract_field(body, selectors["title"], max_len=150)
    if not title:
        title = clean_text(await page.title(), 150)
    event["title"] = title

    event["description"] = await _extract_field(
        body, selectors["description"], max_len=500, min_len=50
    )
    event["date"] = await _extract_field(body, selectors["date"], max_len=200)
    event["venue"] = await _extract_field(body, selectors["venue"], max_len=100)
    event["organizer"] = await _extract_field(
        body, selectors["organizer"], max_len=100
    )
    event["price"] = await _extract_field(body, selectors["price"], max_len=50)
    if not event["price"] and "free" in (
        await body.inner_text("body")
    ).lower()[:2000]:
        event["price"] = "Free"

    event["language"] = detect_language(event["title"], event["description"])
    return event
