"""
complaint_manager.py
--------------------
ComplaintManager class — the central orchestrator.
Coordinates AIAnalyzer, DatabaseManager to handle all business logic.
"""

import logging
from datetime import datetime
from typing import Optional

from models import (
    Complaint, AIResult, ComplaintStatus, Department,
    CATEGORY_TO_DEPARTMENT
)
from ai_analyzer import AIAnalyzer
from database_manager import DatabaseManager
from statistics_engine import StatisticsEngine

logger = logging.getLogger(__name__)


class ComplaintManager:
    """
    High-level business logic layer for the Civic Complaints system.
    Coordinates the AIAnalyzer and DatabaseManager.
    Single point of entry for the FastAPI layer.
    """

    def __init__(self, db: DatabaseManager, ai: AIAnalyzer):
        self.db = db
        self.ai = ai

    # ------------------------------------------------------------------
    # Citizen-facing operations
    # ------------------------------------------------------------------

    def submit_complaint(
        self,
        description: str,
        location: str,
        contact: str = "",
        user_id: Optional[int] = None,
    ) -> Complaint:
        """
        Full complaint submission pipeline:
        1. Run AI analysis (Gemini or fallback)
        2. Auto-assign department based on AI category
        3. Persist to database
        4. Return fully populated Complaint
        """
        if not description or not description.strip():
            raise ValueError("Complaint description cannot be empty.")

        # Step 1: AI analysis
        ai_result: AIResult = self.ai.analyze(description.strip(), location.strip())
        logger.info(
            f"AI result: category={ai_result.category.value}, "
            f"priority={ai_result.priority.value}, "
            f"confidence={ai_result.confidence:.2f}, "
            f"fallback={ai_result.used_fallback}"
        )

        # Step 2: Auto-assign department
        department = CATEGORY_TO_DEPARTMENT.get(ai_result.category, Department.GENERAL)

        # Step 3: Build complaint object
        complaint = Complaint(
            description=description.strip(),
            location=location.strip(),
            contact=contact.strip(),
            user_id=user_id,
            category=ai_result.category,
            priority=ai_result.priority,
            ai_summary=ai_result.summary,
            ai_confidence=ai_result.confidence,
            ai_reasoning=ai_result.reasoning,
            ai_used_fallback=ai_result.used_fallback,
            status=ComplaintStatus.OPEN,
            department=department,
            date_submitted=datetime.utcnow(),
        )

        # Step 4: Save and return
        saved = self.db.save_complaint(complaint)
        logger.info(f"Complaint #{saved.id} saved successfully.")
        return saved

    # ------------------------------------------------------------------
    # Admin-facing operations
    # ------------------------------------------------------------------

    def update_complaint(
        self,
        complaint_id: int,
        status: Optional[str] = None,
        department: Optional[str] = None,
        admin_notes: Optional[str] = None,
    ) -> Optional[Complaint]:
        """Update complaint status/department/notes. Returns updated complaint or None."""
        return self.db.update_complaint(complaint_id, status, department, admin_notes)

    def get_complaint(self, complaint_id: int) -> Optional[Complaint]:
        return self.db.get_complaint_by_id(complaint_id)

    def list_complaints(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Complaint]:
        return self.db.get_all_complaints(
            status=status,
            category=category,
            priority=priority,
            search=search,
            limit=limit,
            offset=offset,
        )

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_statistics(self) -> dict:
        """
        Returns full statistics payload for the admin dashboard.
        Includes summary counts, resolution times, trend data, and matrix.
        """
        all_complaints = self.db.get_all_complaints(limit=10000)
        engine = StatisticsEngine(all_complaints)

        return {
            "summary": engine.compute_summary(),
            "resolution_times": engine.compute_resolution_times(),
            "daily_trend": engine.get_daily_trend(days=30),
            "category_priority_matrix": engine.get_category_priority_matrix(),
            "top_locations": engine.get_top_locations(top_n=8),
            "ai_confidence_stats": engine.get_ai_confidence_stats(),
            "ai_active": self.ai.is_using_ai,
        }
