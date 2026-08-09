"""
statistics_engine.py
--------------------
StatisticsEngine class — computes descriptive statistics and trend data
over the complaint dataset. All calculations use pure Python (no pandas).
"""

import math
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from models import Complaint, ComplaintStatus, Category, Priority


class StatisticsEngine:
    """
    Computes statistics over a list of Complaint objects.
    Provides: counts, mean/median/mode, variance/std-dev, and trend data.
    """

    def __init__(self, complaints: list[Complaint]):
        self.complaints = complaints
        self._total = len(complaints)

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------

    def compute_summary(self) -> dict:
        """High-level breakdown: totals, by category, by priority, by status."""
        by_category = Counter(c.category.value for c in self.complaints)
        by_priority = Counter(c.priority.value for c in self.complaints)
        by_status   = Counter(c.status.value   for c in self.complaints)

        return {
            "total": self._total,
            "by_category": dict(by_category),
            "by_priority": dict(by_priority),
            "by_status": dict(by_status),
            "open_count":        by_status.get("Open", 0),
            "assigned_count":    by_status.get("Assigned", 0),
            "in_progress_count": by_status.get("In Progress", 0),
            "resolved_count":    by_status.get("Resolved", 0),
            "critical_count":    by_priority.get("Critical", 0),
            "high_count":        by_priority.get("High", 0),
        }

    # ------------------------------------------------------------------
    # Resolution time statistics
    # ------------------------------------------------------------------

    def compute_resolution_times(self) -> dict:
        """
        For resolved complaints, compute resolution time in hours.
        Returns mean, median, mode (bucket), variance, std_dev.
        """
        resolved = [
            c for c in self.complaints
            if c.status == ComplaintStatus.RESOLVED and c.date_resolved
        ]

        if not resolved:
            return {
                "count": 0,
                "mean_hours": None,
                "median_hours": None,
                "mode_bucket": None,
                "variance": None,
                "std_dev": None,
                "min_hours": None,
                "max_hours": None,
            }

        hours = sorted(
            (c.date_resolved - c.date_submitted).total_seconds() / 3600
            for c in resolved
        )

        mean_val = self._mean(hours)
        variance = self._variance(hours, mean_val)

        # Bucket mode into: <1h, 1-6h, 6-24h, 24-72h, >72h
        buckets = [self._time_bucket(h) for h in hours]
        mode_bucket = Counter(buckets).most_common(1)[0][0]

        return {
            "count": len(hours),
            "mean_hours": round(mean_val, 2),
            "median_hours": round(self._median(hours), 2),
            "mode_bucket": mode_bucket,
            "variance": round(variance, 2),
            "std_dev": round(math.sqrt(variance), 2),
            "min_hours": round(min(hours), 2),
            "max_hours": round(max(hours), 2),
        }

    # ------------------------------------------------------------------
    # Trend data
    # ------------------------------------------------------------------

    def get_daily_trend(self, days: int = 30) -> list[dict]:
        """
        Returns a list of {date, count} dicts for the last N days,
        filling in 0 for days with no complaints.
        """
        today = datetime.utcnow().date()
        cutoff = today - timedelta(days=days)

        # Build a Counter of submission dates
        date_counts: Counter = Counter()
        for c in self.complaints:
            submitted_date = c.date_submitted.date()
            if submitted_date >= cutoff:
                date_counts[submitted_date] += 1

        # Fill all days in range
        result = []
        for i in range(days + 1):
            day = cutoff + timedelta(days=i)
            result.append({"date": day.isoformat(), "count": date_counts.get(day, 0)})

        return result

    def get_category_priority_matrix(self) -> dict:
        """
        Returns a nested dict: category → priority → count.
        Useful for heatmap visualisation.
        """
        matrix: dict = {}
        for c in self.complaints:
            cat = c.category.value
            pri = c.priority.value
            matrix.setdefault(cat, {})
            matrix[cat][pri] = matrix[cat].get(pri, 0) + 1
        return matrix

    def get_top_locations(self, top_n: int = 10) -> list[dict]:
        """Return the most frequently reported locations."""
        loc_counts = Counter(c.location.strip().lower() for c in self.complaints if c.location.strip())
        return [
            {"location": loc, "count": cnt}
            for loc, cnt in loc_counts.most_common(top_n)
        ]

    def get_ai_confidence_stats(self) -> dict:
        """Descriptive stats on the AI confidence scores."""
        scores = [c.ai_confidence for c in self.complaints if c.ai_confidence > 0]
        if not scores:
            return {"count": 0, "mean": None, "median": None, "std_dev": None}
        mean_val = self._mean(scores)
        variance = self._variance(scores, mean_val)
        return {
            "count": len(scores),
            "mean": round(mean_val, 3),
            "median": round(self._median(sorted(scores)), 3),
            "std_dev": round(math.sqrt(variance), 3),
        }

    # ------------------------------------------------------------------
    # Pure Python statistical helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _median(sorted_values: list[float]) -> float:
        n = len(sorted_values)
        if n == 0:
            return 0.0
        mid = n // 2
        return sorted_values[mid] if n % 2 != 0 else (sorted_values[mid - 1] + sorted_values[mid]) / 2

    @staticmethod
    def _variance(values: list[float], mean_val: Optional[float] = None) -> float:
        if len(values) < 2:
            return 0.0
        mean_val = mean_val if mean_val is not None else sum(values) / len(values)
        return sum((x - mean_val) ** 2 for x in values) / (len(values) - 1)  # sample variance

    @staticmethod
    def _time_bucket(hours: float) -> str:
        if hours < 1:
            return "< 1 hour"
        elif hours < 6:
            return "1–6 hours"
        elif hours < 24:
            return "6–24 hours"
        elif hours < 72:
            return "1–3 days"
        else:
            return "> 3 days"
