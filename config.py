# ─── Search Configuration ─────────────────────────────────────────────────────

SEARCH_KEYWORDS = [
    "tech",
    "AI",
    "machine learning",
    "startup",
    "marketing",
    "digital",
    "web",
    "innovation",
    "entrepreneuriat",
    "data",
]

PARIS_LOCATION = "Paris, France"

# ─── Interest Categories (for scoring) ────────────────────────────────────────
# Each category gets points when keywords match the event title/description.
# weight: points added per matched category (max topic_score caps total)

INTERESTS = {
    "ai_ml": {
        "weight": 15,
        "keywords": [
            "ai", "artificial intelligence", "machine learning", "deep learning",
            "llm", "large language model", "gpt", "chatgpt", "neural network",
            "data science", "nlp", "computer vision", "rag", "agentic",
            "tensorflow", "pytorch", "hugging face", "llama", "claude",
            "intelligence artificielle", "ia", "apprentissage automatique",
        ],
    },
    "startup": {
        "weight": 15,
        "keywords": [
            "startup", "entrepreneur", "fundraising", "pitch", "venture capital",
            "vc", "investor", "seed", "series a", "founder", "scaleup",
            "mvp", "product-market fit", "lean startup", "incubator",
            "accelerator", "business model", "bootstrapping", "business plan",
        ],
    },
    "marketing": {
        "weight": 15,
        "keywords": [
            "marketing", "growth", "seo", "sem", "branding", "acquisition",
            "conversion", "funnel", "lead generation", "content marketing",
            "social media", "digital marketing", "analytics", "cro",
            "marketing automation", "email marketing", "inbound", "ads",
        ],
    },
    "web_dev": {
        "weight": 15,
        "keywords": [
            "react", "python", "javascript", "typescript", "full stack",
            "frontend", "backend", "api", "web development", "software engineering",
            "next.js", "node.js", "fastapi", "django", "docker", "kubernetes",
            "aws", "cloud computing", "architecture", "programming",
            "développement", "développeur", "programmation",
        ],
    },
}

# ─── Format Detection (bonus points) ─────────────────────────────────────────

FORMATS = {
    "workshop": {
        "bonus": 15,
        "keywords": [
            "workshop", "hands-on", "atelier", "pratique", "lab",
            "masterclass", "coding session", "build", "bootcamp",
            "tutorial", "training", "dojo",
        ],
    },
    "conference": {
        "bonus": 10,
        "keywords": [
            "conference", "talk", "keynote", "presentation", "speaker",
            "summit", "panel", "fireside chat",
            "pleniere", "amphi", "symposium",
        ],
    },
    "networking": {
        "bonus": 5,
        "keywords": [
            "networking", "meetup", "afterwork", "drinkup", "social",
            "soiree", "apero", "mixing", "rencontre", "mise en relation",
            "after work",
        ],
    },
}

# ─── Scoring Limits ───────────────────────────────────────────────────────────

SCORING = {
    "topic_max": 60,
    "format_max": 30,
    "description_max": 10,
}

# ─── Output ───────────────────────────────────────────────────────────────────

CSV_COLUMNS = [
    "title",
    "date",
    "time",
    "platform",
    "link",
    "venue",
    "organizer",
    "description",
    "price",
    "format",
    "language",
    "topic_tags",
    "score",
    "scraped_at",
]

OUTPUT_FILE = "events.csv"
