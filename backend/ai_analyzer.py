"""
ai_analyzer.py
--------------
AIAnalyzer class — calls Google Gemini API to classify, prioritize,
and summarize civic complaints. Falls back to a keyword-based classifier
if the API is unavailable or returns an unexpected response.

Uses the new google-genai SDK (google.genai).
"""

import os
import json
import re
import logging
from typing import Optional

from models import AIResult, Category, Priority

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword fallback configuration
# ---------------------------------------------------------------------------

KEYWORD_RULES: list[dict] = [
    {
        "keywords": ["water", "leak", "pipe", "flood", "drain", "sewage", "tap", "burst", "overflow"],
        "category": Category.WATER_DRAINAGE,
        "base_priority": Priority.HIGH,
    },
    {
        "keywords": ["road", "pothole", "pavement", "sidewalk", "bridge", "crack", "tarmac", "traffic"],
        "category": Category.ROADS_PAVEMENTS,
        "base_priority": Priority.MEDIUM,
    },
    {
        "keywords": ["garbage", "waste", "rubbish", "trash", "bin", "litter", "dump", "smell", "odour", "odor"],
        "category": Category.WASTE_SANITATION,
        "base_priority": Priority.MEDIUM,
    },
    {
        "keywords": ["electricity", "power", "light", "streetlight", "wire", "electric", "outage", "blackout", "cable"],
        "category": Category.ELECTRICITY,
        "base_priority": Priority.HIGH,
    },
    {
        "keywords": ["park", "tree", "grass", "garden", "playground", "green", "plants", "bench"],
        "category": Category.PARKS_GREEN,
        "base_priority": Priority.LOW,
    },
    {
        "keywords": ["noise", "loud", "music", "construction", "disturb", "night", "party", "sound"],
        "category": Category.NOISE_DISTURBANCE,
        "base_priority": Priority.MEDIUM,
    },
    {
        "keywords": ["safety", "crime", "robbery", "theft", "dangerous", "fight", "threat", "attack", "assault"],
        "category": Category.PUBLIC_SAFETY,
        "base_priority": Priority.CRITICAL,
    },
]

URGENT_KEYWORDS = ["urgent", "emergency", "critical", "danger", "immediately", "severe", "serious", "hazard"]
HIGH_KEYWORDS   = ["major", "big", "large", "significant", "main", "broken", "blocked"]
LOW_KEYWORDS    = ["minor", "small", "slight", "little", "cosmetic", "aesthetic"]


class AIAnalyzer:
    """
    Analyzes civic complaints using the Google Gemini API (google-genai SDK).
    Provides category classification, priority scoring, and complaint summarization.
    Falls back to keyword-based analysis if the API is unavailable.
    """

    GEMINI_PROMPT = """You are an expert AI assistant for a government civic complaint management system.
Analyze the following citizen complaint and respond ONLY with a valid JSON object — no markdown, no extra text.

Complaint Description: "{description}"
Reported Location: "{location}"

Respond with this exact JSON structure:
{{
  "category": "<one of: Water/Drainage | Roads/Pavements | Waste/Sanitation | Electricity | Parks/Green Spaces | Noise/Disturbance | Public Safety | Other>",
  "priority": "<one of: Low | Medium | High | Critical>",
  "summary": "<one concise sentence describing the problem for the repair team>",
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<brief explanation of why you chose this category and priority>"
}}

Priority guide:
- Critical: immediate safety/health risk (e.g., burst main pipe, live electrical wire, crime in progress)
- High: significant disruption affecting many people (e.g., major road damage, sewage overflow, power outage)
- Medium: moderate issue affecting daily life (e.g., potholes, broken streetlight, overflowing bins)
- Low: minor inconvenience (e.g., faded paint, minor park maintenance needed)"""

    def __init__(self, api_key: Optional[str] = None):
        self._api_available = False
        self._client = None
        self._model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
        api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=api_key)
                self._api_available = True
                logger.info(f"AIAnalyzer: Gemini API initialized with model {self._model}.")
            except Exception as e:
                logger.warning(f"AIAnalyzer: Gemini init failed — {e}. Using fallback classifier.")
        else:
            logger.warning("AIAnalyzer: No GEMINI_API_KEY found. Using fallback keyword classifier.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, description: str, location: str = "") -> AIResult:
        """
        Main entry point. Returns a structured AIResult for a complaint.
        Tries Gemini API first; falls back to keyword classifier on any error.
        """
        if not description or not description.strip():
            return self._empty_result()

        if self._api_available and self._client:
            try:
                return self._analyze_with_gemini(description.strip(), location.strip())
            except Exception as e:
                logger.error(f"AIAnalyzer: Gemini call failed — {e}. Falling back.")

        return self._fallback_classify(description.strip(), location.strip())

    @property
    def is_using_ai(self) -> bool:
        """Returns True if the Gemini API is active."""
        return self._api_available

    # ------------------------------------------------------------------
    # Gemini API path (google-genai SDK)
    # ------------------------------------------------------------------

    def _analyze_with_gemini(self, description: str, location: str) -> AIResult:
        prompt = self.GEMINI_PROMPT.format(description=description, location=location)

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
        )
        raw_text = response.text.strip()

        # Extract JSON — handle cases where Gemini wraps it in ```json ... ```
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON in Gemini response: {raw_text[:200]}")

        data = json.loads(json_match.group())

        # Validate and normalise enum values
        try:
            category = Category(data["category"])
        except (KeyError, ValueError):
            category = Category.OTHER

        try:
            priority = Priority(data["priority"])
        except (KeyError, ValueError):
            priority = Priority.MEDIUM

        confidence = float(data.get("confidence", 0.8))
        confidence = max(0.0, min(1.0, confidence))

        return AIResult(
            category=category,
            priority=priority,
            summary=str(data.get("summary", "Civic issue reported."))[:300],
            confidence=confidence,
            reasoning=str(data.get("reasoning", ""))[:500],
            used_fallback=False,
        )

    # ------------------------------------------------------------------
    # Keyword fallback classifier
    # ------------------------------------------------------------------

    def _fallback_classify(self, description: str, location: str = "") -> AIResult:
        """
        Lightweight keyword-based classifier used when Gemini is unavailable.
        Matches the complaint text against known keyword rules.
        """
        text_lower = description.lower()
        best_match = None
        best_score = 0

        for rule in KEYWORD_RULES:
            score = sum(1 for kw in rule["keywords"] if kw in text_lower)
            if score > best_score:
                best_score = score
                best_match = rule

        if best_match:
            category = best_match["category"]
            priority = best_match["base_priority"]
        else:
            category = Category.OTHER
            priority = Priority.MEDIUM

        # Adjust priority based on urgency words
        if any(kw in text_lower for kw in URGENT_KEYWORDS):
            priority = Priority.CRITICAL
        elif any(kw in text_lower for kw in HIGH_KEYWORDS) and priority == Priority.MEDIUM:
            priority = Priority.HIGH
        elif any(kw in text_lower for kw in LOW_KEYWORDS) and priority != Priority.CRITICAL:
            priority = Priority.LOW

        confidence = min(0.4 + best_score * 0.08, 0.72)

        summary = self._generate_fallback_summary(description, category)
        reasoning = (
            f"Keyword-based classification (AI API unavailable). "
            f"Matched {best_score} keyword(s) for '{category.value}' category."
        )

        return AIResult(
            category=category,
            priority=priority,
            summary=summary,
            confidence=confidence,
            reasoning=reasoning,
            used_fallback=True,
        )

    def _generate_fallback_summary(self, description: str, category: Category) -> str:
        truncated = description[:120].rstrip()
        if len(description) > 120:
            truncated += "..."
        return f"{category.value} issue reported: {truncated}"

    def _empty_result(self) -> AIResult:
        return AIResult(
            category=Category.OTHER,
            priority=Priority.LOW,
            summary="No description provided.",
            confidence=0.0,
            reasoning="Empty complaint description submitted.",
            used_fallback=True,
        )
