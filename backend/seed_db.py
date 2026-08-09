"""
seed_db.py
----------
Utility script to seed the SQLite database with realistic mock complaints
for the AI Smart Civic Services app. This ensures the dashboard charts
and stats render beautifully on first load.
"""

import sys
import os
import random
from datetime import datetime, timedelta

# Add backend directory to path so we can import models and managers
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import Complaint, Category, Priority, ComplaintStatus, Department, CATEGORY_TO_DEPARTMENT
from database_manager import DatabaseManager

MOCK_COMPLAINTS = [
    {
        "description": "Large water main burst at the intersection of Maple St and 5th Ave. Water is gushing out rapidly and starting to flood the nearby pedestrian walk. Street is becoming impassable.",
        "location": "Maple St & 5th Ave",
        "category": Category.WATER_DRAINAGE,
        "priority": Priority.CRITICAL,
        "ai_summary": "Burst water main causing flooding near Maple St.",
        "ai_confidence": 0.95,
        "ai_reasoning": "Large volume burst water main presents immediate risk of infrastructure damage and flooding, categorized as Critical Water/Drainage.",
        "status": ComplaintStatus.IN_PROGRESS,
        "department": Department.WATER_AUTHORITY,
        "days_ago": 3,
        "resolved_days_ago": None,
        "admin_notes": "Emergency response crew dispatched. Main valve shut off, repair ongoing."
    },
    {
        "description": "Deep pothole in the middle of the right lane on Highway 101. It is hard to see at night and has already damaged two cars' tires today. Needs urgent patch work.",
        "location": "Highway 101, Mile Marker 14",
        "category": Category.ROADS_PAVEMENTS,
        "priority": Priority.HIGH,
        "ai_summary": "Severe pothole on Highway 101 damaging vehicle tires.",
        "ai_confidence": 0.92,
        "ai_reasoning": "Pothole on high-speed road causing active vehicle damage warrants High priority Roads/Pavements rating.",
        "status": ComplaintStatus.ASSIGNED,
        "department": Department.PUBLIC_WORKS,
        "days_ago": 1,
        "resolved_days_ago": None,
        "admin_notes": "Assigned to the road maintenance team for temporary cold patch repair."
    },
    {
        "description": "Garbage piles have accumulated behind the community market. It hasn't been collected for over a week, leading to a strong bad smell and attracting stray animals.",
        "location": "Behind Central Community Market",
        "category": Category.WASTE_SANITATION,
        "priority": Priority.HIGH,
        "ai_summary": "Accumulated garbage pile behind community market causing odor.",
        "ai_confidence": 0.89,
        "ai_reasoning": "Uncollected public waste causing sanitation hazards and odor, classified as High priority Waste/Sanitation.",
        "status": ComplaintStatus.RESOLVED,
        "department": Department.WASTE_MANAGEMENT,
        "days_ago": 10,
        "resolved_days_ago": 8,
        "admin_notes": "Special cleanup truck dispatched. Market owners reminded of disposal regulations."
    },
    {
        "description": "Streetlight has been flickering and is now completely out near the dark alleyway. This corner is now pitch black at night, making residents feel unsafe walking home.",
        "location": "Corner of Oak Lane and Pine St",
        "category": Category.ELECTRICITY,
        "priority": Priority.MEDIUM,
        "ai_summary": "Broken streetlight causing dark area at Pine St intersection.",
        "ai_confidence": 0.91,
        "ai_reasoning": "Broken streetlight reduces public safety at night but is not an immediate life-safety hazard, classified as Medium Electricity.",
        "status": ComplaintStatus.RESOLVED,
        "department": Department.ELECTRICITY_BOARD,
        "days_ago": 5,
        "resolved_days_ago": 4,
        "admin_notes": "Bulb replaced and wiring checked by electricity crew."
    },
    {
        "description": "The swing set in the neighborhood playground is broken. One of the chains snapped, leaving a heavy metal swing hanging precariously. Dangerous for young children playing.",
        "location": "Sunnyvale Community Park",
        "category": Category.PARKS_GREEN,
        "priority": Priority.MEDIUM,
        "ai_summary": "Broken swing chain at Sunnyvale playground.",
        "ai_confidence": 0.88,
        "ai_reasoning": "Broken playground equipment presents moderate danger to children, classified as Medium Parks/Green Spaces.",
        "status": ComplaintStatus.OPEN,
        "department": Department.PARKS_RECREATION,
        "days_ago": 0,
        "resolved_days_ago": None,
        "admin_notes": ""
    },
    {
        "description": "Loud construction noise from the commercial site continues well past 11 PM on weekdays. Heavy machinery is operating, keeping the entire neighborhood awake.",
        "location": "88 Industrial Way development",
        "category": Category.NOISE_DISTURBANCE,
        "priority": Priority.MEDIUM,
        "ai_summary": "Late night construction noise exceeding curfew limits.",
        "ai_confidence": 0.93,
        "ai_reasoning": "Late night noise violation disrupts residents but is non-life-threatening. Medium Noise/Disturbance.",
        "status": ComplaintStatus.RESOLVED,
        "department": Department.NOISE_CONTROL,
        "days_ago": 7,
        "resolved_days_ago": 6,
        "admin_notes": "Noise control officer visited the site and issued a warning letter to the contractor."
    },
    {
        "description": "Suspicious group of people loitering around the closed convenience store, aggressively shouting at passersby. Several residents report feeling intimidated.",
        "location": "Broad Street Plaza, near 24-7 Shop",
        "category": Category.PUBLIC_SAFETY,
        "priority": Priority.HIGH,
        "ai_summary": "Loitering and aggressive behavior near closed store.",
        "ai_confidence": 0.85,
        "ai_reasoning": "Intimidating behavior and loitering in public spaces flagged as Public Safety (High Priority).",
        "status": ComplaintStatus.RESOLVED,
        "department": Department.POLICE,
        "days_ago": 4,
        "resolved_days_ago": 3,
        "admin_notes": "Patrol car dispatched. Individuals dispersed. Regular nighttime checks requested."
    },
    {
        "description": "An old, dry tree branch is hanging low over the active sidewalk. If a strong wind blows, it looks like it will fall directly on pedestrians walking below.",
        "location": "Jalan Bukit, outside Public Library",
        "category": Category.PARKS_GREEN,
        "priority": Priority.HIGH,
        "ai_summary": "Hazardous hanging tree branch above busy sidewalk.",
        "ai_confidence": 0.90,
        "ai_reasoning": "Imminent hazard of a falling tree branch over a pedestrian walkway warrants High priority Parks/Green Spaces classification.",
        "status": ComplaintStatus.IN_PROGRESS,
        "department": Department.PARKS_RECREATION,
        "days_ago": 2,
        "resolved_days_ago": None,
        "admin_notes": "Tree trimmer crew scheduled to cut down the branch."
    },
    {
        "description": "A storm drain is completely clogged with leaves, plastic bottles, and silt. It has started raining, and the street corner is already starting to accumulate a pool of water.",
        "location": "87 Commercial Road",
        "category": Category.WATER_DRAINAGE,
        "priority": Priority.MEDIUM,
        "ai_summary": "Clogged storm drain causing street pooling.",
        "ai_confidence": 0.94,
        "ai_reasoning": "Clogged drain causing minor flooding on roadway, classified as Medium Water/Drainage.",
        "status": ComplaintStatus.OPEN,
        "department": Department.WATER_AUTHORITY,
        "days_ago": 0,
        "resolved_days_ago": None,
        "admin_notes": ""
    },
    {
        "description": "There is a sparking transformer on the power pole near the school. It makes loud popping noises occasionally and drops sparks on the dry grass below.",
        "location": "School Lane, behind St. Jude Academy",
        "category": Category.ELECTRICITY,
        "priority": Priority.CRITICAL,
        "ai_summary": "Sparking transformer on power pole near school field.",
        "ai_confidence": 0.96,
        "ai_reasoning": "Sparking electrical infrastructure near a school poses high risk of fire and electrocution, classified as Critical Electricity.",
        "status": ComplaintStatus.IN_PROGRESS,
        "department": Department.ELECTRICITY_BOARD,
        "days_ago": 1,
        "resolved_days_ago": None,
        "admin_notes": "Urgent alert sent to Grid Maintenance team. Grid isolated transformer."
    },
    {
        "description": "Graffiti on the community center walls has been defaced with offensive language. It needs to be cleaned or painted over before children visit for weekend activities.",
        "location": "Eastside Community Center",
        "category": Category.OTHER,
        "priority": Priority.LOW,
        "ai_summary": "Offensive graffiti on community center walls.",
        "ai_confidence": 0.82,
        "ai_reasoning": "Aesthetic vandalization, minor threat. Categorized as Low priority Other.",
        "status": ComplaintStatus.RESOLVED,
        "department": Department.GENERAL,
        "days_ago": 15,
        "resolved_days_ago": 12,
        "admin_notes": "Graffiti painted over by local community cleaning volunteer unit."
    },
    {
        "description": "The sidewalk curb ramp is completely broken and has cracked into pieces, making it impossible for wheelchair users to cross the street safely.",
        "location": "Intersection of 2nd St and Grand Ave",
        "category": Category.ROADS_PAVEMENTS,
        "priority": Priority.MEDIUM,
        "ai_summary": "Damaged wheelchair ramp at crosswalk intersection.",
        "ai_confidence": 0.90,
        "ai_reasoning": "Damaged accessibility ramp prevents safe street crossings but isn't an emergency, classified as Medium Roads/Pavements.",
        "status": ComplaintStatus.ASSIGNED,
        "department": Department.PUBLIC_WORKS,
        "days_ago": 6,
        "resolved_days_ago": None,
        "admin_notes": "Inspected. Added to the concrete replacement queue for the upcoming week."
    }
]

def seed():
    print("AI Smart Civic Services: Starting DB seeding...")
    db = DatabaseManager()
    
    # Check if there are already records
    existing = db.get_complaint_count()
    if existing > 0:
        print(f"Database already contains {existing} complaints. Skipping seeding to prevent duplicates.")
        return

    base_time = datetime.utcnow()

    for idx, data in enumerate(MOCK_COMPLAINTS):
        # Calculate mock dates
        date_submitted = base_time - timedelta(days=data["days_ago"], hours=random.randint(1, 23))
        
        date_resolved = None
        if data["resolved_days_ago"] is not None:
            date_resolved = base_time - timedelta(days=data["resolved_days_ago"], hours=random.randint(1, 23))

        c = Complaint(
            description=data["description"],
            location=data["location"],
            contact=f"citizen_{idx+1}@example.com",
            category=data["category"],
            priority=data["priority"],
            ai_summary=data["ai_summary"],
            ai_confidence=data["ai_confidence"],
            ai_reasoning=data["ai_reasoning"],
            ai_used_fallback=False,
            status=data["status"],
            department=data["department"],
            admin_notes=data["admin_notes"],
            date_submitted=date_submitted,
            date_resolved=date_resolved
        )
        db.save_complaint(c)
        print(f"Saved complaint #{idx+1}: {c.location} ({c.category.value})")

    print("DB Seeding completed successfully!")

if __name__ == "__main__":
    seed()
