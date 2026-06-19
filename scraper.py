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
import sys

from playwright.async_api import async_playwright, Page

from config import SEARCH_KEYWORDS, CSV_COLUMNS, OUTPUT_FILE
from browser import create_context, safe_goto, extract_event, random_delay
from scoring import score_event

logger = logging.getLogger(__name__)


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

        page_text = await page.inner_text("body")
        if "sign up" in page_text.lower() and "event" not in page_text.lower()[:500]:
            logger.warning("Meetup: signup wall detected, skipping")
            continue

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

            event = await extract_event(page, href, "Meetup")
            if event:
                events.append(event)

    for e in events:
        score_event(e)
    events.sort(key=lambda e: e.get("score", 0), reverse=True)

    logger.info(f"Meetup: total unique events: {len(events)}")
    return events


async def scrape_luma(page: Page) -> list[dict]:
    events = []
    seen_links: set = set()

    url = "https://lu.ma/discover?region=Paris"
    logger.info("Luma: searching")

    ok = await safe_goto(page, url)
    if not ok:
        return events

    await asyncio.sleep(random_delay(3, 5))

    for i in range(4):
        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(random_delay(1, 2))

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

        event = await extract_event(page, href, "Luma")
        if event:
            events.append(event)

    for e in events:
        score_event(e)
    events.sort(key=lambda e: e.get("score", 0), reverse=True)

    logger.info(f"Luma: total unique events: {len(events)}")
    return events


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

    if sorted_events:
        top = sorted_events[0]
        print(f"\n ★ Best match: {top['title']} ({top['platform']}) — Score: {top['score']}")
        print(f"   {top['link']}")


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
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

        try:
            ctx = await create_context(browser)
            page = await ctx.new_page()
            meetup_events = await scrape_meetup(page)
            all_events.extend(meetup_events)
            await ctx.close()
        except Exception as e:
            logger.error(f"Meetup failed: {e}")

        try:
            ctx = await create_context(browser)
            page = await ctx.new_page()
            luma_events = await scrape_luma(page)
            all_events.extend(luma_events)
            await ctx.close()
        except Exception as e:
            logger.error(f"Luma failed: {e}")

        await browser.close()

    for ev in all_events:
        score_event(ev)
    all_events.sort(key=lambda e: e.get("score", 0), reverse=True)

    existing = load_existing_events(OUTPUT_FILE)
    new_events = deduplicate_events(all_events, existing)

    if new_events:
        append_to_csv(OUTPUT_FILE, new_events, CSV_COLUMNS)
        logger.info(f"Appended {len(new_events)} new events (total in CSV: {len(existing) + len(new_events)})")
    else:
        logger.info("No new events found")

    print_summary(all_events)

    if not all_events:
        logger.warning("Zero events scraped — sites may have changed layout")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
