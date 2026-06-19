import pytest
import sys
sys.path.insert(0, ".")

from scraper import score_event, detect_language, clean_text


class TestCleanText:
    def test_collapses_whitespace(self):
        assert clean_text("hello   world") == "hello world"

    def test_strips_outer_spaces(self):
        assert clean_text("  foo bar  ") == "foo bar"

    def test_truncates_with_ellipsis(self):
        result = clean_text("a" * 100, max_len=10)
        assert result == "aaaaaaaaaa..."
        assert len(result) == 13

    def test_no_truncation_when_under_max(self):
        text = "short text"
        assert clean_text(text, max_len=50) == text

    def test_empty_string(self):
        assert clean_text("") == ""


class TestDetectLanguage:
    def test_detects_french(self):
        title = "Atelier IA à Paris"
        desc = "Inscription gratuite pour cet atelier"
        assert detect_language(title, desc) == "French"

    def test_detects_english(self):
        title = "AI Workshop in Paris"
        desc = "Join us for a hands-on workshop"
        assert detect_language(title, desc) == "English"

    def test_returns_empty_for_few_keywords(self):
        title = "Event"
        desc = "Some generic description with no matches"
        assert detect_language(title, desc) == ""

    def test_french_outranks_english(self):
        title = "Conférence IA"
        desc = "Atelier gratuit avec intervenant — inscription obligatoire"
        assert detect_language(title, desc) == "French"

    def test_english_outranks_french(self):
        title = "Tech Talk Meetup"
        desc = "Workshop with speaker — register now to attend"
        assert detect_language(title, desc) == "English"


class TestScoreEvent:
    def test_scores_zero_for_empty_event(self):
        event = {"title": "", "description": ""}
        result = score_event(event)
        assert result["score"] == 0
        assert result["topic_tags"] == ""

    def test_matches_ai_ml_keywords(self):
        event = {"title": "AI Workshop with LLMs", "description": "Build with RAG and LangChain"}
        result = score_event(event)
        assert result["score"] > 0
        assert "ai_ml" in result["topic_tags"]

    def test_matches_startup_keywords(self):
        event = {"title": "Startup Pitch Night", "description": "Founders present to VCs"}
        result = score_event(event)
        assert result["score"] > 0
        assert "startup" in result["topic_tags"]

    def test_multiple_topic_matches_stack(self):
        event = {"title": "AI Startup Marketing Workshop", "description": "Growth hacks for AI founders"}
        result = score_event(event)
        tags = result["topic_tags"]
        assert "ai_ml" in tags
        assert "startup" in tags
        # Each match = 15 points, so with 3+ topics it should cap at 60
        assert result["score"] >= 15

    def test_topic_score_capped(self):
        event = {"title": "AI ML DL NLP LLM Agent RAG Startup Marketing Tech event"}
        description = " ".join([
            "artificial intelligence", "machine learning", "data science",
            "deep learning", "python", "typescript", "react", "founder",
            "venture capital", "fundraising", "growth", "seo", "branding",
        ])
        event["description"] = description
        result = score_event(event)
        assert result["score"] <= 75  # topic_max(60) + format_max(30) + desc_max(10) - but format likely 0 here

    def test_format_detection_workshop(self):
        event = {"title": "Hands-on Workshop", "description": "Coding session with practical exercises"}
        result = score_event(event)
        assert result["format"] == "workshop"

    def test_format_detection_conference(self):
        event = {"title": "Tech Conference 2025", "description": "Keynote speakers and panels"}
        result = score_event(event)
        assert result["format"] == "conference"

    def test_description_bonus(self):
        short_event = {"title": "Test", "description": "Short"}
        long_event = {"title": "Test", "description": "x" * 500}
        short_result = score_event(short_event)
        long_result = score_event(long_event)
        assert long_result["score"] > short_result["score"]

    def test_preserves_existing_fields(self):
        event = {"title": "AI Talk", "description": "A talk about AI", "venue": "Paris"}
        result = score_event(event)
        assert result["venue"] == "Paris"

    def test_handles_none_description(self):
        event = {"title": "Test", "description": None}
        result = score_event(event)
        assert result["score"] == 0
