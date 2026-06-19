# Tech Debt Audit — Paris Events Scraper

Generated: 2026-06-19
Audit scope: entire repository (~1,190 LOC, 10 source files)
Tools: `pytest --cov`, `ast` analysis, manual code review

## Executive Summary

- **3 Critical, 8 High, 9 Medium, 5 Low** findings
- **54% overall test coverage** — the scraping engine (the whole point of the project) has **0% coverage**
- Biggest debt concentration: `scraper.py` — a 661-line god file housing all scraping, extraction, scoring, CSV, and main orchestration logic
- The two platform scrapers (`extract_meetup_event` / `extract_luma_event`) are ~85% duplicated code; difference is only CSS selector lists
- CI workflow references a non-existent `tests/test_e2e.py` — the scheduled CI run will fail
- No package manifest (`pyproject.toml`), no linting config, no lockfile — project won't build reproducibly

## Architectural Mental Model

The system is a single-module Python CLI that uses Playwright to scrape two event platforms (Meetup, Luma) for Paris tech/marketing events, scores them via keyword matching, deduplicates against a local CSV, and appends new results. There are no classes, no packages — just 16 top-level functions in `scraper.py` and a constants module `config.py`. The test suite covers the scoring/dedup/CSO logic but leaves the entire browser-automation path untested. The repo has 2 commits, both created today, suggesting the project is new — so the debt is mostly about missing structural foundations rather than accumulated rot.

## Findings

| ID | Category | File:Line | Severity | Effort | Description | Recommendation |
|----|----------|-----------|----------|--------|-------------|----------------|
| F001 | Test debt | `.github/workflows/test.yml:33` | Critical | S | CI references `--ignore=tests/test_e2e.py` but file doesn't exist. Schedule-triggered runs invoke `pytest tests/test_e2e.py -v` which will fail. | Remove the e2e reference or create the test file. |
| F002 | Test debt | `scraper.py:182-519` | Critical | L | The entire Playwright scraping engine (Meetup + Luma scrape + extract functions, ~340 lines) has 0% test coverage. No tests for `scrape_meetup`, `scrape_luma`, `extract_meetup_event`, `extract_luma_event`, `safe_goto`, `try_click_cookie_banner`, or `create_context`. | Add integration tests using Playwright's mocking/record/replay, or at minimum unit tests for the extraction helpers by providing HTML fixtures. |
| F003 | Architectural decay | `scraper.py:239-357`, `scraper.py:409-519` | Critical | M | `extract_meetup_event` and `extract_luma_event` are ~85% identical (same dict construction, same field extraction loop pattern, same fallback logic, same language detection call). Only the CSS selector lists differ. | Extract a shared `extract_event(page, url, platform, selector_map)` function. Pass per-platform selectors as a config dict. |
| F004 | Architectural decay | `scraper.py` (entire file) | High | M | God file: 661 lines, 16 top-level functions, mixing 5 concerns (stealth config, scraping, scoring, CSV ops, CLI). 56% of total repo LOC. | Split into `scrapers/meetup.py`, `scrapers/luma.py`, `scoring.py`, `storage.py`, `cli.py`. Keep `main()` as thin orchestration. |
| F005 | Error handling | `scraper.py:118-126`, `scraper.py:129-138`, `scraper.py:262-264`, `scraper.py:272-273`, `scraper.py:286-309`, `scraper.py:312-352`, `scraper.py:431-514` | High | M | Broad `except Exception: continue` / `except Exception: pass` throughout extraction. Silently swallows selector failures, making debugging layout changes impossible. At minimum, log the exception at DEBUG level. | Replace bare excepts with specific exceptions (e.g., `except TimeoutError`). Add `logger.debug` for swallowed errors. |
| F006 | Error handling | `scraper.py:239-255`, `scraper.py:409-424` | High | S | When `safe_goto` fails, the function returns a blank event dict with only `scraped_at` populated. Downstream code scores and processes it as if it were valid. Downstream `score_event` at line 143 calls `event.get('title', '')` which returns empty string, producing a score of 0 — but the blank row still gets written to CSV. | Return `None` instead of a blank dict. Update callers to `if event is not None: ...`. |
| F007 | Test debt | `.github/workflows/test.yml:37` | High | L | Weekly CI runs a full e2e scrape (no mocks) against live Meetup/Luma. This depends on external sites, network, and Playwright system deps. It will break unpredictably and has no assertion beyond "doesn't crash." | If kept, add assertions (expected fields present, score > 0). Better: substitute with a mocked Playwright test. |
| F008 | Type & contract debt | `scraper.py:143`, `scraper.py:239`, `scraper.py:409`, `scraper.py:524`, `scraper.py:536`, `scraper.py:560`, `scraper.py:573` | High | S | All functions return or accept bare `dict` as "event" type. No `TypedDict`, `dataclass`, or `NamedTuple`. Impossible to verify at caller side that required keys exist. | Define `class Event(TypedDict)` or a `@dataclass` with all CSV_COLUMNS as fields. Use it in function signatures. |
| F009 | Architectural decay | repo root | Medium | S | No `pyproject.toml` or `setup.py`. Project metadata, dependencies, Python version requirement, and entry point live only in `README.md` or `requirements.txt`. Can't `pip install -e .` or run tests without `sys.path.insert(0, '.')`. | Create `pyproject.toml` with `[project]`, `[tool.setuptools.packages.find]`, and `[project.scripts]`. |
| F010 | Consistency rot | `scraper.py:182-236` vs `scraper.py:362-406` | Medium | M | Meetup scrapes iteratively per keyword (10 sequential page loads); Luma scrolls once. Different strategies for different platforms is fine, but the orchestrator (`main`) should not need to care. Additionally, both functions re-sort by score after appending events, but `main` at line 638-640 re-sorts again — triplicate sorting. | Extract the search/scroll abstraction into a strategy pattern or function parameter. Remove duplicate sorting in `main`. |
| F011 | Error handling | `scraper.py:31-35` | Medium | S | `logging.basicConfig` called at module import time with hardcoded format/level. Any import of `scraper` configures the root logger globally. Breaks for anyone importing `score_event` programmatically. | Move logging config into `main()`. Use `logging.getLogger(__name__)` without basicConfig at module level. |
| F012 | Performance | `scraper.py:186-197` | Medium | M | Meetup loops over 10 keywords sequentially, each requiring a full page load, cookie dismissal, and wait. This is ~30-50 seconds of wall-clock time for what could be a single search with broader terms or parallel requests. | Reduce keyword set or use parallel contexts. At minimum, deduplicate across keywords before scoring (already done for links, but page loads still happen). |
| F013 | Observability | `scraper.py:31-35`, `scraper.py:124`, `scraper.py:137`, `scraper.py:204`, `scraper.py:218`, `scraper.py:235`, `scraper.py:389`, `scraper.py:405`, `scraper.py:532`, `scraper.py:622`, `scraper.py:632`, `scraper.py:648`, `scraper.py:650`, `scraper.py:656` | Medium | S | All logging is plain `logger.info`/`logger.warning` with f-string messages. No structured fields (event count, duration, URL, platform). Cannot be parsed by structured log aggregators. | Use `extra=` dict parameter or switch to `structlog` / `loguru` for structured log events. |
| F014 | Type & contract debt | `scraper.py:87``, `scraper.py:143` | Medium | S | `detect_language` returns bare string (`"French"` / `"English"` / `""`). `score_event` mutates the input dict (side effect) and returns it. Both patterns invite bugs at call sites. | Use `typing.Literal["French", "English", ""]` for return type. Make `score_event` return a new dict or use a frozen dataclass. |
| F015 | Config debt | `config.py:3-14`, `config.py:22-119` | Medium | S | All configuration is Python code (constants module). No env var overrides, no `.env` file, no `--config` CLI flag. Running in CI (weekly_scrape.yml line 39-42) uses hardcoded defaults with no way to customize per environment. | Add `python-dotenv` or `os.environ.get()` fallbacks for at least `OUTPUT_FILE` and `SEARCH_KEYWORDS`. |
| F016 | Dependency debt | `requirements.txt:1` | Medium | S | Only dependency is `playwright>=1.48,<2.0`. No lockfile means builds can produce different results. Pinning to a range without a lockfile is better than nothing, but `pip freeze > requirements-lock.txt` would make CI reproducible. | Add `requirements-lock.txt` or switch to `pip-tools` / `uv`. |
| F017 | Documentation drift | `.github/workflows/test.yml:33-37` | Medium | S | CI comment says "Run e2e smoke test" but the file doesn't exist. The test workflow's schedule trigger will break. | Either create `tests/test_e2e.py` or remove the schedule trigger and e2e step. |
| F018 | Security hygiene | `scraper.py:524-533` | Low | S | `load_existing_events` at line 531 catches all exceptions and returns `[]`. A corrupted CSV with malicious content would be silently ignored rather than rejected. | Be specific about exception types. Consider validating CSV content against `CSV_COLUMNS` schema. |
| F019 | Consistency rot | `tests/test_scoring.py:3`, `tests/test_storage.py:6` | Low | S | Both test files do `sys.path.insert(0, ".")` to import `scraper`. Works but is fragile — breaks if run from a different working directory. | Either install package (`pip install -e .`) or use `-m pytest` from repo root with proper package structure. |
| F020 | Config debt | `.gitignore:1-4` | Low | S | `events.csv` (the output file) is not in `.gitignore`. The weekly CI workflow (`weekly_scrape.yml:47-51`) commits it. This pollutes git history with binary-like generated data over time. | Add `events.csv` to `.gitignore` if committed data is intentional, or document that the automated commit is by design. |
| F021 | Consistency rot | `scraper.py:182-236` | Low | M | `scrape_meetup` limits to 10 results per keyword (`[:10]` at line 220). `scrape_luma` limits to 15 (`[:15]` at line 391). Different limits with no rationale. | Unify limits in config. |
| F022 | Performance | `scraper.py:376-378` | Low | S | Luma scrolling loop uses fixed 4 iterations × 800px. If Luma changes their page layout (infinite scroll vs. paginated), this silently produces fewer results. | Scroll until "no more results" sentinel is found, or measure scroll height changes. |

## Top 5 — If You Fix Nothing Else, Fix These

### 1. F003 — Deduplicate extract_meetup_event / extract_luma_event

These two functions (`scraper.py:239` and `scraper.py:409`) are structurally identical. Every field extraction follows the same pattern: try selectors in order, fall back to next, clean text, break on first hit. The only differences are the selector lists.

**Refactor sketch:**
```python
# scraper.py — add a shared extractor
PLATFORM_SELECTORS = {
    "Meetup": {
        "description": ['[data-testid="event-description"]', '[class*="description"]', ...],
        "date": ["time", '[data-testid="event-time"]', ...],
        "venue": ['[data-testid="venue"]', ...],
        # ...
    },
    "Luma": {
        "description": ['[class*="description"]', '[class*="content"]', ...],
        "date": ["time", '[class*="date"]', ...],
        # ...
    },
}

async def extract_event(page: Page, url: str, platform: str) -> Optional[Event]:
    event = Event(platform=platform, link=url, ...)
    ok = await safe_goto(page, url, timeout=20000)
    if not ok:
        return None
    try:
        await page.wait_for_selector("h1", timeout=8000)
    except TimeoutError:
        pass
    selectors = PLATFORM_SELECTORS[platform]
    event.title = await _extract_field(page, selectors["title"], ...)
    event.description = await _extract_field(page, selectors["description"], ...)
    # ... etc
    return event
```

### 2. F001 — Fix the CI / e2e test gap

The test workflow has a dangling reference to `tests/test_e2e.py`. The simplest fix: remove the schedule trigger and the e2e step from `test.yml`, or create a real smoke test. At minimum, the workflow must not fail on schedule runs.

### 3. F006 — Return None instead of blank dict on scrape failure

When `safe_goto` fails (`scraper.py:257`, `scraper.py:427`), returning a blank dict pollutes the event stream with score-0 rows that have empty titles. These get appended to CSV.

**Fix:**
```python
async def extract_meetup_event(page, url) -> Optional[dict]:
    ok = await safe_goto(page, url, timeout=20000)
    if not ok:
        return None  # was: return blank event dict
    # ...
```

Callers (`scrape_meetup` line 226-228) already check `if event:` so this works correctly.

### 4. F008 — Typed event contract

Define a TypedDict or dataclass instead of bare dict passing across all functions.

```python
from typing import TypedDict

class Event(TypedDict, total=False):
    title: str
    date: str
    time: str
    platform: str
    link: str
    venue: str
    organizer: str
    description: str
    price: str
    format: str
    language: str
    topic_tags: str
    score: float
    scraped_at: str
```

This catches key typos and missing field errors at type-check time.

### 5. F004 — Split the god file

`scraper.py` does everything. Minimum viable split:

```
scraper/
  __init__.py
  config.py          # move config.py here (or keep at root)
  browser.py         # create_context, safe_goto, try_click_cookie_banner, STEALTH_SCRIPT
  meetup.py          # scrape_meetup, extract_meetup_event
  luma.py            # scrape_luma, extract_luma_event
  scoring.py         # score_event, detect_language, clean_text
  storage.py         # load_existing_events, deduplicate_events, append_to_csv
  cli.py             # print_summary, main
```

## Quick Wins

- [ ] F001 — Remove `--ignore=tests/test_e2e.py` flag and the e2e schedule step from `test.yml` (effort: minutes, no code change)
- [ ] F006 — Change `return event` to `return None` in extract functions when `safe_goto` fails (effort: minutes)
- [ ] F008 — Add `Event` TypedDict definition (effort: 15 min)
- [ ] F011 — Move `logging.basicConfig` into `main()` (effort: 5 min)
- [ ] F020 — Add `events.csv` to `.gitignore` (effort: 1 min, but verify the CI commit workflow is intended first)
- [ ] F014 — Add `Literal` return type to `detect_language` (effort: 2 min)
- [ ] F016 — Run `pip freeze > requirements-lock.txt` (effort: 1 min)
- [ ] F019 — Replace `sys.path.insert(0, ".")` with proper install (effort: depends on F009)

## Things That Look Bad But Are Actually Fine

- **The broad `except Exception: continue` in `try_click_cookie_banner` (lines 118-126).** The intent is to attempt multiple selector patterns, most of which won't match. A try-per-pattern is the correct approach since you don't know which banners are present. Logging each failure at DEBUG would be noise. This is pragmatic.

- **`sys.path.insert(0, ".")` in test files (test_scoring.py:3, test_storage.py:6).** Looks like a hack, but without a package manifest (F009), there's no other way to import from the root. Fix the root cause (missing `pyproject.toml`) rather than these two lines.

- **Sequential keyword search for Meetup (10 iterations, ~30-50s).** For a weekly cron that runs once per week, this is acceptable. Parallelizing would add connection-management complexity and risk rate-limiting from Meetup. The current approach is intentionally conservative.

- **No type hints on internal helper functions like `random_delay`, `clean_text`, `detect_language`.** The project is small (~1,190 LOC) and single-author. Full strict typing on every helper is low-value for a tool this size. The bigger gap is the cross-function dict interface (F008), which is already flagged.

- **Hardcoded `USER_AGENTS` list with three Chrome 126 variants (lines 53-57).** Looks stale-able but actually works correctly: `random.choice(USER_AGENTS)` picks one per browser context, and having 3 options with different OS fingerprints is enough to avoid trivial bot detection. Over-engineering this into a large rotation pool would add maintenance without measurable benefit.

- **`from typing import Optional` at line 17 but only used in 5 function signatures.** Could be a star-import or just missing. For a file this size, single-import-from-typing is fine. Flagged only for completeness; not actionable.

## Open Questions for the Maintainer

- **Is `events.csv` supposed to be version-controlled?** The CI workflow (`.github/workflows/weekly_scrape.yml:44-51`) commits it back to the repo. If yes, `.gitignore` should NOT list it. If no, add it and change the CI to use a release artifact instead.
- **Is `test_e2e.py` a planned file that hasn't been created yet, or dead config?** The workflow references it in two places (`--ignore=...` and direct invocation). If it's planned, when? If not, the references should be removed.
- **The two scraper strategies (keyword iteration for Meetup, scroll-for-more for Luma) — were these chosen to match each platform's UX, or is one just a prototype?** If Meetup supports a broader search URL parameter, the keyword loop could be collapsed into one query.
- **Is the weekly scrape intended to be the sole "production" use, or are you planning to run this ad-hoc?** This affects whether adding a CLI config flag (F015) or keeping Python constants is the right approach.
- **Duplicated `fr_score` and `en_score` word lists in `detect_language` (lines 89-96)** contain "conference" / "Conférence" (french list) and "workshop", "talk", "meetup" (english list) — these work but aren't linguistically rigorous. Is this intentional (good enough heuristic) or placeholder data?

## Coverage Summary

| File | Covered | Missed | Coverage |
|------|---------|--------|----------|
| `config.py` | 7 | 0 | 100% |
| `scraper.py` | 98 | 266 | 27% |
| `tests/test_scoring.py` | 90 | 0 | 100% |
| `tests/test_storage.py` | 114 | 0 | 100% |
| **Total** | **309** | **266** | **54%** |

Uncovered code: all 8 async functions (browser setup, navigation, page extraction, main orchestration), legacy CSV read error path, and `print_summary`. The core value of the project — actually scraping event websites — has zero automated verification.
