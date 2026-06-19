#!/usr/bin/env python3
"""
Paris Tech & Marketing Events Scraper
Scrapes Meetup + Luma for events in Paris, scores them by relevance to your interests.
Appends new events to events.csv.
Run: python scraper.py
"""

import asyncio
import csv
import logging
import os
import random
import re
import sys
from datetime import datetime, timezone
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser

from config import (
    SEARCH_KEYWORDS,
    PARIS_LOCATION,
    INTERESTS,
    FORMATS,
    SCORING,
    CSV_COLUMNS,
    OUTPUT_FILE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Stealth ───────────────────────────────────────────────────────────────────

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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def clean_text(text: str, max_len: int = 0) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    if max_len and len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def detect_language(title: str, description: str) -> str:
    text = (title + " " + description).lower()
    french_words = [
        "conference", "atelier", "rencontre", "presentation", "gratuit",
        "inscription", "bonjour", "programme", "intervenant", "participer",
    ]
    english_words = [
        "workshop", "talk", "meetup", "register", "rsvp",
        "learn", "join", "welcome", "speaker", "attend",
    ]
    fr_score = sum(1 for w in french_words if re.search(rf'(?<![a-z]){w}(?![a-z])', text))
    en_score = sum(1 for w in english_words if re.search(rf'(?<![a-z]){w}(?![a-z])', text))
    if fr_score > en_score:
        return "French"
    elif en_score > fr_score:
        return "English"
    return ""


async def try_click_cookie_banner(page: Page):
    """Accept cookie banners if present."""
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
            continue


async def safe_goto(page: Page, url: str, timeout: int = 30000) -> bool:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await asyncio.sleep(random_delay(2, 4))
        await try_click_cookie_banner(page)
        await page.wait_for_load_state("networkidle", timeout=10000)
        return True
    except Exception as e:
        logger.warning(f"Navigation failed: {url[:60]}... ({e})")
        return False


# ─── Scoring ──────────────────────────────────────────────────────────────────

def score_event(event: dict) -> dict:
    text = f"{event.get('title', '')} {event.get('description', '')}".lower()

    topic_score = 0
    matched_topics = []
    for category, config in INTERESTS.items():
        for kw in config["keywords"]:
            if re.search(rf'(?<![a-z]){re.escape(kw.lower())}(?![a-z])', text):
                topic_score += config["weight"]
                matched_topics.append(category)
                break

    topic_score = min(topic_score, SCORING["topic_max"])

    format_score = 0
    detected_formats = []
    for fmt, config in FORMATS.items():
        for kw in config["keywords"]:
            if re.search(rf'(?<![a-z]){re.escape(kw.lower())}(?![a-z])', text):
                format_score += config["bonus"]
                detected_formats.append(fmt)
                break

    format_score = min(format_score, SCORING["format_max"])

    desc = event.get("description", "") or ""
    desc_score = min(len(desc) / 200, 1.0) * SCORING["description_max"]

    total = round(topic_score + format_score + desc_score, 1)

    event["topic_tags"] = ", ".join(matched_topics) if matched_topics else ""
    event["format"] = ", ".join(detected_formats) if detected_formats else ""
    event["score"] = total

    return event


# ─── Meetup Scraper ───────────────────────────────────────────────────────────

async def scrape_meetup(page: Page) -> list[dict]:
    events = []
    seen_links: set = set()

    for keyword in SEARCH_KEYWORDS:
        url = (
            "https://www.meetup.com/find/events/"
            f"?allMeetups=true"
            f"&keywords={keyword}"
            f"&location=Paris%2C%20France"
            f"&source=EVENTS"
        )
        logger.info(f"Meetup: searching '{keyword}'")

        ok = await safe_goto(page, url)
        if not ok:
            continue

        await asyncio.sleep(random_delay(3, 6))

        # detect signup wall
        page_text = await page.inner_text("body")
        if "sign up" in page_text.lower() and "event" not in page_text.lower()[:500]:
            logger.warning("Meetup: signup wall detected, skipping")
            continue

        # collect event links
        links = await page.eval_on_selector_all(
            "a[href*='/events/']",
            "els => els.map(el => ({href: el.href, text: el.innerText.trim()}))",
        )
        valid = [
            l for l in links
            if "/events/" in l["href"]
            and not l["href"].endswith("/events/")
        ]
        logger.info(f"Meetup: found {len(valid)} event links for '{keyword}'")

        for entry in valid[:10]:
            href = entry["href"]
            if href in seen_links:
                continue
            seen_links.add(href)

            event = await extract_meetup_event(page, href)
            if event:
                events.append(event)

    # sort unique by score descending
    for e in events:
        score_event(e)
    events.sort(key=lambda e: e.get("score", 0), reverse=True)

    logger.info(f"Meetup: total unique events: {len(events)}")
    return events


async def extract_meetup_event(page: Page, url: str) -> Optional[dict]:
    event = {
        "title": "",
        "date": "",
        "time": "",
        "platform": "Meetup",
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
        return event

    try:
        await page.wait_for_selector("h1", timeout=8000)
    except Exception:
        pass

    body = page
    # Title
    try:
        h1 = await body.query_selector("h1")
        if h1:
            event["title"] = clean_text(await h1.inner_text(), 150)
    except Exception:
        pass
    if not event["title"]:
        event["title"] = clean_text(await page.title(), 150)

    # Description
    for sel in [
        '[data-testid="event-description"]',
        '[class*="description"]',
        '[itemprop="description"]',
        "main",
        "article",
    ]:
        try:
            el = await body.query_selector(sel)
            if el:
                text = clean_text(await el.inner_text(), 500)
                if len(text) > 50:
                    event["description"] = text
                    break
        except Exception:
            continue

    # Date
    for sel in [
        "time",
        '[data-testid="event-time"]',
        '[class*="dateTime"]',
        '[class*="date"]',
    ]:
        try:
            el = await body.query_selector(sel)
            if el:
                dt = clean_text(await el.inner_text(), 200)
                if dt:
                    event["date"] = dt
                    break
        except Exception:
            continue

    # Venue
    for sel in [
        '[data-testid="venue"]',
        '[class*="venue"]',
        '[class*="location"]',
    ]:
        try:
            el = await body.query_selector(sel)
            if el:
                event["venue"] = clean_text(await el.inner_text(), 100)
                break
        except Exception:
            continue

    # Organizer
    for sel in [
        '[data-testid="group-name"]',
        '[class*="groupName"]',
        '[class*="organizer"]',
        "a[href*='/groups/']",
    ]:
        try:
            el = await body.query_selector(sel)
            if el:
                event["organizer"] = clean_text(await el.inner_text(), 100)
                break
        except Exception:
            continue

    # Price
    for sel in [
        '[class*="price"]',
        '[class*="ticket"]',
    ]:
        try:
            el = await body.query_selector(sel)
            if el:
                event["price"] = clean_text(await el.inner_text(), 50)
                break
        except Exception:
            continue
    if "free" in (await body.inner_text("body")).lower()[:2000] and not event["price"]:
        event["price"] = "Free"

    event["language"] = detect_language(event["title"], event["description"])
    return event


# ─── Luma Scraper ─────────────────────────────────────────────────────────────

async def scrape_luma(page: Page) -> list[dict]:
    events = []
    seen_links: set = set()

    url = "https://lu.ma/discover?region=Paris"
    logger.info("Luma: searching")

    ok = await safe_goto(page, url)
    if not ok:
        return events

    await asyncio.sleep(random_delay(3, 5))

    # scroll to load more
    for i in range(4):
        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(random_delay(1, 2))

    # collect event links
    links = await page.eval_on_selector_all(
        "a[href*='/event/']",
        "els => els.map(el => ({href: el.href, text: el.innerText.trim()}))",
    )
    valid = [
        l for l in links
        if "/event/" in l["href"] and l["text"]
    ]
    logger.info(f"Luma: found {len(valid)} event links")

    for entry in valid[:15]:
        href = entry["href"]
        if href in seen_links:
            continue
        seen_links.add(href)

        event = await extract_luma_event(page, href)
        if event:
            events.append(event)

    for e in events:
        score_event(e)
    events.sort(key=lambda e: e.get("score", 0), reverse=True)

    logger.info(f"Luma: total unique events: {len(events)}")
    return events


async def extract_luma_event(page: Page, url: str) -> Optional[dict]:
    event = {
        "title": "",
        "date": "",
        "time": "",
        "platform": "Luma",
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
        return event

    try:
        await page.wait_for_selector("h1", timeout=8000)
    except Exception:
        pass

    # Title
    try:
        h1 = await page.query_selector("h1")
        if h1:
            event["title"] = clean_text(await h1.inner_text(), 150)
    except Exception:
        pass
    if not event["title"]:
        event["title"] = clean_text(await page.title(), 150)

    # Description
    for sel in [
        '[class*="description"]',
        '[class*="content"]',
        "main",
        "article",
    ]:
        try:
            el = await page.query_selector(sel)
            if el:
                text = clean_text(await el.inner_text(), 500)
                if len(text) > 50:
                    event["description"] = text
                    break
        except Exception:
            continue

    # Date
    for sel in ["time", '[class*="date"]', '[class*="time"]', '[class*="schedule"]']:
        try:
            el = await page.query_selector(sel)
            if el:
                dt = clean_text(await el.inner_text(), 200)
                if dt:
                    event["date"] = dt
                    break
        except Exception:
            continue

    # Venue
    for sel in [
        '[class*="location"]',
        '[class*="venue"]',
        '[class*="address"]',
    ]:
        try:
            el = await page.query_selector(sel)
            if el:
                event["venue"] = clean_text(await el.inner_text(), 100)
                break
        except Exception:
            continue

    # Organizer
    for sel in [
        '[class*="host"]',
        '[class*="organizer"]',
        "a[href*='/calendar/']",
    ]:
        try:
            el = await page.query_selector(sel)
            if el:
                event["organizer"] = clean_text(await el.inner_text(), 100)
                break
        except Exception:
            continue

    # Price
    for sel in [
        '[class*="price"]',
        '[class*="ticket"]',
    ]:
        try:
            el = await page.query_selector(sel)
            if el:
                event["price"] = clean_text(await el.inner_text(), 50)
                break
        except Exception:
            continue
    if "free" in (await page.inner_text("body")).lower()[:2000] and not event["price"]:
        event["price"] = "Free"

    event["language"] = detect_language(event["title"], event["description"])
    return event


# ─── CSV ops ───────────────────────────────────────────────────────────────────

def load_existing_events(filepath: str) -> list[dict]:
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        logger.warning(f"Could not read existing CSV: {e}")
        return []


def deduplicate_events(new_events: list[dict], existing_events: list[dict]) -> list[dict]:
    known = set()
    for ev in existing_events:
        key = (
            ev.get("title", "").strip().lower(),
            ev.get("date", "").strip(),
            ev.get("platform", "").strip(),
        )
        known.add(key)

    deduped = []
    seen_this_run = set()
    for ev in new_events:
        key = (
            ev.get("title", "").strip().lower(),
            ev.get("date", "").strip(),
            ev.get("platform", "").strip(),
        )
        if key not in known and key not in seen_this_run:
            seen_this_run.add(key)
            deduped.append(ev)
    return deduped


def append_to_csv(filepath: str, events: list[dict], columns: list[str]):
    exists = os.path.exists(filepath)
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if not exists:
            writer.writeheader()
        for ev in events:
            row = {col: ev.get(col, "") for col in columns}
            writer.writerow(row)


# ─── Summary ──────────────────────────────────────────────────────────────────

def print_summary(all_events: list[dict]):
    sorted_events = sorted(all_events, key=lambda e: e.get("score", 0), reverse=True)
    print(f"\n{'─'*60}")
    print(f" TOP {min(10, len(sorted_events))} EVENTS BY SCORE")
    print(f"{'─'*60}")
    print(f" {'Scored':>6}  {'Platform':<8}  {'Title':<45}")
    print(f"{'─'*60}")
    for ev in sorted_events[:10]:
        s = ev.get("score", 0)
        m = "★ " if s >= 50 else "  "
        plat = ev.get("platform", "?")[:7]
        title = ev.get("title", "?")[:44]
        print(f" {m}{s:>5.1f}  {plat:<8}  {title}")
    print(f"{'─'*60}")
    print(f" Total new: {len(sorted_events)}")

    # Highlight top pick
    if sorted_events:
        top = sorted_events[0]
        print(f"\n ★ Best match: {top['title']} ({top['platform']}) — Score: {top['score']}")
        print(f"   {top['link']}")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    logger.info("=" * 50)
    logger.info("Paris Events Scraper starting")
    logger.info(f"Keywords: {', '.join(SEARCH_KEYWORDS)}")

    all_events: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )

        # Meetup
        try:
            ctx = await create_context(browser)
            page = await ctx.new_page()
            meetup_events = await scrape_meetup(page)
            all_events.extend(meetup_events)
            await ctx.close()
        except Exception as e:
            logger.error(f"Meetup failed: {e}")

        # Luma
        try:
            ctx = await create_context(browser)
            page = await ctx.new_page()
            luma_events = await scrape_luma(page)
            all_events.extend(luma_events)
            await ctx.close()
        except Exception as e:
            logger.error(f"Luma failed: {e}")

        await browser.close()

    # Score + sort
    for ev in all_events:
        score_event(ev)
    all_events.sort(key=lambda e: e.get("score", 0), reverse=True)

    # Dedup against existing CSV
    existing = load_existing_events(OUTPUT_FILE)
    new_events = deduplicate_events(all_events, existing)

    if new_events:
        append_to_csv(OUTPUT_FILE, new_events, CSV_COLUMNS)
        logger.info(f"Appended {len(new_events)} new events (total in CSV: {len(existing) + len(new_events)})")
    else:
        logger.info("No new events found")

    print_summary(all_events)

    # Raise if nothing was found at all (so CI/email alert triggers)
    if not all_events:
        logger.warning("Zero events scraped — sites may have changed layout")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
