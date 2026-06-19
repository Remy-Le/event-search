import re
from typing import Literal, TypedDict

from config import INTERESTS, FORMATS, SCORING


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


def clean_text(text: str, max_len: int = 0) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    if max_len and len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def detect_language(title: str, description: str) -> Literal["French", "English", ""]:
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
