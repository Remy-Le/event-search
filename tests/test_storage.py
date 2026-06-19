import csv
import os
import tempfile
import pytest
import sys
sys.path.insert(0, ".")

from scraper import deduplicate_events, load_existing_events, append_to_csv, CSV_COLUMNS


class TestDeduplicate:
    def make_event(self, title, date="2025-06-01", platform="Meetup"):
        return {"title": title, "date": date, "platform": platform}

    def test_deduplicates_by_title_date_platform(self):
        existing = [self.make_event("AI Workshop", "2025-06-01", "Meetup")]
        new = [self.make_event("AI Workshop", "2025-06-01", "Meetup")]
        result = deduplicate_events(new, existing)
        assert len(result) == 0

    def test_allows_same_title_different_date(self):
        existing = [self.make_event("AI Workshop", "2025-06-01", "Meetup")]
        new = [self.make_event("AI Workshop", "2025-06-02", "Meetup")]
        result = deduplicate_events(new, existing)
        assert len(result) == 1

    def test_allows_same_title_different_platform(self):
        existing = [self.make_event("AI Workshop", "2025-06-01", "Meetup")]
        new = [self.make_event("AI Workshop", "2025-06-01", "Luma")]
        result = deduplicate_events(new, existing)
        assert len(result) == 1

    def test_handles_empty_existing(self):
        new = [self.make_event("AI Workshop")]
        result = deduplicate_events(new, [])
        assert len(result) == 1

    def test_handles_empty_new(self):
        result = deduplicate_events([], [self.make_event("AI Workshop")])
        assert result == []

    def test_case_insensitive_title_match(self):
        existing = [self.make_event("AI Workshop", "2025-06-01", "Meetup")]
        new = [self.make_event("ai workshop", "2025-06-01", "Meetup")]
        result = deduplicate_events(new, existing)
        assert len(result) == 0

    def test_deduplicates_within_new_events(self):
        existing = []
        new = [
            self.make_event("AI Workshop", "2025-06-01", "Meetup"),
            self.make_event("AI Workshop", "2025-06-01", "Meetup"),
        ]
        result = deduplicate_events(new, existing)
        assert len(result) == 1

    def test_missing_fields_handled_gracefully(self):
        existing = [{}]
        new = [{"title": "Event"}]
        result = deduplicate_events(new, existing)
        assert len(result) == 1


class TestLoadExistingEvents:
    def test_returns_empty_for_missing_file(self):
        result = load_existing_events("/nonexistent/path.csv")
        assert result == []

    def test_returns_events_from_valid_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            f.write("title,date,platform\nEvent1,2025-01-01,Meetup\nEvent2,2025-02-01,Luma\n")
            path = f.name
        try:
            result = load_existing_events(path)
            assert len(result) == 2
            assert result[0]["title"] == "Event1"
            assert result[1]["platform"] == "Luma"
        finally:
            os.unlink(path)

    def test_returns_empty_for_empty_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
            f.write("title,date,platform\n")
            path = f.name
        try:
            result = load_existing_events(path)
            assert result == []
        finally:
            os.unlink(path)

    def test_returns_empty_for_corrupted_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("not a csv file at all \x00\x01\x02")
            path = f.name
        try:
            result = load_existing_events(path)
            assert result == []
        finally:
            os.unlink(path)


class TestAppendToCsv:
    def test_writes_header_for_new_file(self):
        path = tempfile.mktemp(suffix=".csv")
        try:
            append_to_csv(path, [], CSV_COLUMNS)
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                assert reader.fieldnames == CSV_COLUMNS
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_appends_rows(self):
        path = tempfile.mktemp(suffix=".csv")
        try:
            events = [{"title": "Test Event", "score": 42}]
            append_to_csv(path, events, CSV_COLUMNS)
            with open(path, newline="") as f:
                rows = list(csv.DictReader(f))
            assert len(rows) == 1
            assert rows[0]["title"] == "Test Event"
            assert rows[0]["score"] == "42"
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_appends_without_duplicating_header(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            writer.writerow(["Old Event"] + [""] * (len(CSV_COLUMNS) - 1))
            path = f.name
        try:
            events = [{"title": "New Event"}]
            append_to_csv(path, events, CSV_COLUMNS)
            with open(path, newline="") as f:
                rows = list(csv.DictReader(f))
            assert len(rows) == 2
            assert rows[0]["title"] == "Old Event"
            assert rows[1]["title"] == "New Event"
        finally:
            os.unlink(path)
