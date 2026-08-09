"""
database_manager.py
-------------------
DatabaseManager class — the single point of contact for all SQLite operations.
Follows the OOP pattern: one class, one responsibility.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional

from models import Complaint, Category, Priority, ComplaintStatus, Department, User, UserRole


DB_PATH = os.environ.get("DB_PATH", "civic_complaints.db")


class DatabaseManager:
    """
    Manages all database interactions for the Civic Complaints system.
    Uses SQLite with context managers for safe connection handling.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_database()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row   # enables column-name access
        conn.execute("PRAGMA journal_mode=WAL;")  # better concurrency
        return conn

    def _init_database(self) -> None:
        """Create tables if they don't already exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS complaints (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    description      TEXT    NOT NULL,
                    location         TEXT    NOT NULL,
                    contact          TEXT    DEFAULT '',
                    category         TEXT    NOT NULL DEFAULT 'Other',
                    priority         TEXT    NOT NULL DEFAULT 'Medium',
                    ai_summary       TEXT    DEFAULT '',
                    ai_confidence    REAL    DEFAULT 0.0,
                    ai_reasoning     TEXT    DEFAULT '',
                    ai_used_fallback INTEGER DEFAULT 0,
                    status           TEXT    NOT NULL DEFAULT 'Open',
                    department       TEXT    NOT NULL DEFAULT 'Unassigned',
                    admin_notes      TEXT    DEFAULT '',
                    date_submitted   TEXT    NOT NULL,
                    date_resolved    TEXT    DEFAULT NULL
                )
            """)
            # Index for common filters
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status   ON complaints(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON complaints(category);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_priority ON complaints(priority);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date     ON complaints(date_submitted);")

            # ── Users Table ────────────────────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    email         TEXT    NOT NULL UNIQUE,
                    display_name  TEXT    NOT NULL DEFAULT '',
                    role          TEXT    NOT NULL DEFAULT 'citizen',
                    password_hash TEXT    DEFAULT NULL,
                    google_id     TEXT    UNIQUE DEFAULT NULL,
                    avatar_url    TEXT    DEFAULT NULL,
                    is_active     INTEGER NOT NULL DEFAULT 1,
                    created_at    TEXT    NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email     ON users(email);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);")
            conn.commit()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save_complaint(self, complaint: Complaint) -> Complaint:
        """Insert a new complaint and return it with its generated id."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO complaints
                    (description, location, contact, category, priority,
                     ai_summary, ai_confidence, ai_reasoning, ai_used_fallback,
                     status, department, admin_notes, date_submitted, date_resolved)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                complaint.description,
                complaint.location,
                complaint.contact,
                complaint.category.value,
                complaint.priority.value,
                complaint.ai_summary,
                complaint.ai_confidence,
                complaint.ai_reasoning,
                int(complaint.ai_used_fallback),
                complaint.status.value,
                complaint.department.value,
                complaint.admin_notes,
                complaint.date_submitted.isoformat(),
                complaint.date_resolved.isoformat() if complaint.date_resolved else None,
            ))
            conn.commit()
            complaint.id = cursor.lastrowid
        return complaint

    def update_complaint(
        self,
        complaint_id: int,
        status: Optional[str] = None,
        department: Optional[str] = None,
        admin_notes: Optional[str] = None,
    ) -> Optional[Complaint]:
        """Update a complaint's status, department, or admin notes."""
        existing = self.get_complaint_by_id(complaint_id)
        if not existing:
            return None

        new_status = ComplaintStatus(status) if status else existing.status
        new_dept = Department(department) if department else existing.department
        new_notes = admin_notes if admin_notes is not None else existing.admin_notes

        # Set resolved timestamp when status transitions to Resolved or Successful
        date_resolved = existing.date_resolved
        if new_status in (ComplaintStatus.RESOLVED, ComplaintStatus.SUCCESSFUL) and not date_resolved:
            date_resolved = datetime.utcnow()

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE complaints
                SET status = ?, department = ?, admin_notes = ?, date_resolved = ?
                WHERE id = ?
            """, (
                new_status.value,
                new_dept.value,
                new_notes,
                date_resolved.isoformat() if date_resolved else None,
                complaint_id,
            ))
            conn.commit()

        return self.get_complaint_by_id(complaint_id)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_complaint_by_id(self, complaint_id: int) -> Optional[Complaint]:
        """Fetch a single complaint by primary key."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM complaints WHERE id = ?", (complaint_id,)
            ).fetchone()
        return Complaint.from_dict(dict(row)) if row else None

    def get_all_complaints(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Complaint]:
        """Fetch complaints with optional filtering."""
        query = "SELECT * FROM complaints WHERE 1=1"
        params: list = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if category:
            query += " AND category = ?"
            params.append(category)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        if search:
            query += " AND (description LIKE ? OR location LIKE ? OR ai_summary LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like])

        query += " ORDER BY date_submitted DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [Complaint.from_dict(dict(r)) for r in rows]

    def get_complaint_count(self, **filters) -> int:
        """Return total count matching optional filters."""
        query = "SELECT COUNT(*) FROM complaints WHERE 1=1"
        params: list = []
        if filters.get("status"):
            query += " AND status = ?"
            params.append(filters["status"])
        if filters.get("category"):
            query += " AND category = ?"
            params.append(filters["category"])
        if filters.get("priority"):
            query += " AND priority = ?"
            params.append(filters["priority"])

        with self._get_connection() as conn:
            return conn.execute(query, params).fetchone()[0]

    def get_raw_statistics_data(self) -> list[dict]:
        """Return all complaints as dicts for statistical processing."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM complaints").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # User operations
    # ------------------------------------------------------------------

    def create_user(self, user: User) -> User:
        """Insert a new user and return it with its generated id."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO users
                       (email, display_name, role, password_hash, google_id, avatar_url, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user.email,
                    user.display_name,
                    user.role.value,
                    user.password_hash,
                    user.google_id,
                    user.avatar_url,
                    1 if user.is_active else 0,
                    user.created_at.isoformat(),
                ),
            )
            user.id = cursor.lastrowid
        return user

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Retrieve a user by email address."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return self._row_to_user(row)

    def get_user_by_google_id(self, google_id: str) -> Optional[User]:
        """Retrieve a user by Google OAuth ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE google_id = ?", (google_id,)).fetchone()
        return self._row_to_user(row)

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Retrieve a user by primary key."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._row_to_user(row)

    def _row_to_user(self, row) -> Optional[User]:
        if not row:
            return None
        d = dict(row)
        return User(
            id=d["id"],
            email=d["email"],
            display_name=d["display_name"],
            role=UserRole(d["role"]),
            password_hash=d.get("password_hash"),
            google_id=d.get("google_id"),
            avatar_url=d.get("avatar_url"),
            is_active=bool(d["is_active"]),
            created_at=datetime.fromisoformat(d["created_at"]),
        )
    def get_daily_counts(self, days: int = 30) -> list[dict]:
        """Return complaint counts grouped by day for the last N days."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    DATE(date_submitted) as day,
                    COUNT(*) as count
                FROM complaints
                WHERE date_submitted >= DATE('now', ? || ' days')
                GROUP BY DATE(date_submitted)
                ORDER BY day ASC
            """, (f"-{days}",)).fetchall()
        return [dict(r) for r in rows]
