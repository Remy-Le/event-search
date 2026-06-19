# Paris Tech & Marketing Events Scraper

Scrapes Meetup and Luma for tech/marketing events in Paris, scores them by relevance to your interests, and appends new ones to `events.csv`.

## Features
- Scrapes **Meetup** and **Luma** event listings for Paris
- **Stealth** Playwright (random user-agent, viewport, webdriver spoofing)
- **Smart scoring** by topic (AI/ML, startup, marketing, web dev) + format (workshop, conference, networking)
- French/English **language detection**
- Cookie banner auto-dismissal
- **Deduplication** against existing CSV entries
- Sorted output with top picks highlighted

## Requirements
- Python 3.10+
- Playwright (installs Chromium)

## Setup
```bash
pip install -r requirements.txt
playwright install chromium
```

## Configuration
Edit `config.py` to adjust:
- `SEARCH_KEYWORDS` — search terms
- `INTERESTS` — topic weights and keywords
- `FORMATS` — format bonuses
- `SCORING` — max score caps
- `OUTPUT_FILE` — CSV path

## Usage
```bash
python scraper.py
```

Appends new events to `events.csv` and prints a top-10 scoreboard.

## Testing
```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

35 unit tests covering scoring, language detection, dedup, and CSV operations.

## How it works
1. Opens a stealth Playwright browser
2. Searches Meetup for each keyword in Paris
3. Visits Luma's Paris discover page, scrolls for more results
4. Extracts event details (title, date, venue, price, etc.)
5. Scores each event by topic relevance + format preference + description length
6. Deduplicates against existing `events.csv`
7. Appends and prints a summary

## CI
Tests run on push/PR. Full e2e scrape runs weekly via GitHub Actions.

## License
MIT
