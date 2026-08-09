"""
models.py
---------
Core data models for the AI Smart Civic Services system.
Defines the Complaint dataclass and all associated enums.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Category(str, Enum):
    """Categories of civic complaints."""
    WATER_DRAINAGE = "Water/Drainage"
    ROADS_PAVEMENTS = "Roads/Pavements"
    WASTE_SANITATION = "Waste/Sanitation"
    ELECTRICITY = "Electricity"
    PARKS_GREEN = "Parks/Green Spaces"
    NOISE_DISTURBANCE = "Noise/Disturbance"
    PUBLIC_SAFETY = "Public Safety"
    OTHER = "Other"


class Priority(str, Enum):
    """AI-assessed urgency level of a complaint."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class ComplaintStatus(str, Enum):
    """Lifecycle status of a complaint."""
    OPEN = "Open"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"
    SUCCESSFUL = "Successful"


class Department(str, Enum):
    """Government departments that handle complaints."""
    WATER_AUTHORITY = "Water Authority"
    PUBLIC_WORKS = "Public Works"
    WASTE_MANAGEMENT = "Waste Management"
    ELECTRICITY_BOARD = "Electricity Board"
    PARKS_RECREATION = "Parks & Recreation"
    NOISE_CONTROL = "Noise Control Unit"
    POLICE = "Police / Safety"
    GENERAL = "General Services"
    UNASSIGNED = "Unassigned"


# Map category → default department
CATEGORY_TO_DEPARTMENT: dict[Category, Department] = {
    Category.WATER_DRAINAGE: Department.WATER_AUTHORITY,
    Category.ROADS_PAVEMENTS: Department.PUBLIC_WORKS,
    Category.WASTE_SANITATION: Department.WASTE_MANAGEMENT,
    Category.ELECTRICITY: Department.ELECTRICITY_BOARD,
    Category.PARKS_GREEN: Department.PARKS_RECREATION,
    Category.NOISE_DISTURBANCE: Department.NOISE_CONTROL,
    Category.PUBLIC_SAFETY: Department.POLICE,
    Category.OTHER: Department.GENERAL,
}


@dataclass
class AIResult:
    """Structured output from the AIAnalyzer."""
    category: Category
    priority: Priority
    summary: str
    confidence: float          # 0.0 – 1.0
    reasoning: str
    used_fallback: bool = False  # True if Gemini API was unavailable


@dataclass
class Complaint:
    """
    Core domain object representing a single citizen complaint.
    All fields are populated at submission time; status fields evolve over time.
    """
    # Core fields (citizen-provided)
    description: str
    location: str

    # AI-generated fields
    category: Category = Category.OTHER
    priority: Priority = Priority.MEDIUM
    ai_summary: str = ""
    ai_confidence: float = 0.0
    ai_reasoning: str = ""
    ai_used_fallback: bool = False

    # Admin/lifecycle fields
    status: ComplaintStatus = ComplaintStatus.OPEN
    department: Department = Department.UNASSIGNED
    admin_notes: str = ""

    # Optional citizen contact
    contact: str = ""

    # Auto-managed
    id: Optional[int] = None
    date_submitted: datetime = field(default_factory=datetime.utcnow)
    date_resolved: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Serialize complaint to a JSON-serializable dict."""
        return {
            "id": self.id,
            "description": self.description,
            "location": self.location,
            "contact": self.contact,
            "category": self.category.value,
            "priority": self.priority.value,
            "ai_summary": self.ai_summary,
            "ai_confidence": round(self.ai_confidence, 2),
            "ai_reasoning": self.ai_reasoning,
            "ai_used_fallback": self.ai_used_fallback,
            "status": self.status.value,
            "department": self.department.value,
            "admin_notes": self.admin_notes,
            "date_submitted": self.date_submitted.isoformat(),
            "date_resolved": self.date_resolved.isoformat() if self.date_resolved else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Complaint":
        """Deserialize a complaint from a database row dict."""
        date_resolved = None
        if data.get("date_resolved"):
            date_resolved = datetime.fromisoformat(data["date_resolved"])

        return cls(
            id=data.get("id"),
            description=data["description"],
            location=data["location"],
            contact=data.get("contact", ""),
            category=Category(data["category"]),
            priority=Priority(data["priority"]),
            ai_summary=data.get("ai_summary", ""),
            ai_confidence=data.get("ai_confidence", 0.0),
            ai_reasoning=data.get("ai_reasoning", ""),
            ai_used_fallback=bool(data.get("ai_used_fallback", False)),
            status=ComplaintStatus(data["status"]),
            department=Department(data["department"]),
            admin_notes=data.get("admin_notes", ""),
            date_submitted=datetime.fromisoformat(data["date_submitted"]),
            date_resolved=date_resolved,
        )


# ---------------------------------------------------------------------------
# User & Authentication Models
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    """Roles for access control."""
    ADMIN   = "admin"
    CITIZEN = "citizen"


@dataclass
class User:
    """Represents an authenticated user account."""
    email:         str
    display_name:  str
    role:          UserRole = UserRole.CITIZEN
    password_hash: Optional[str] = None   # None for Google OAuth-only users
    google_id:     Optional[str] = None   # None for email/password users
    avatar_url:    Optional[str] = None
    id:            Optional[int] = None
    created_at:    datetime = field(default_factory=datetime.utcnow)
    is_active:     bool = True

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "email":        self.email,
            "display_name": self.display_name,
            "role":         self.role.value,
            "avatar_url":   self.avatar_url,
            "created_at":   self.created_at.isoformat(),
        }
