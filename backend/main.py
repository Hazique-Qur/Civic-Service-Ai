"""
main.py
-------
FastAPI application entry point.
Defines all REST API endpoints and wires up the OOP layer.
"""

# Load .env file automatically (development convenience)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Workaround for passlib + bcrypt >= 4.0.0 compatibility on newer Python runtimes
try:
    import bcrypt
    _orig_hashpw = bcrypt.hashpw
    def _patched_hashpw(password, salt):
        if isinstance(password, str):
            password_bytes = password.encode('utf-8')
        else:
            password_bytes = password
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
        return _orig_hashpw(password_bytes, salt)
    bcrypt.hashpw = _patched_hashpw
except ImportError:
    pass

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Header, Cookie, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
import httpx

from models import ComplaintStatus, Department, Category, Priority, User, UserRole
from database_manager import DatabaseManager
from ai_analyzer import AIAnalyzer
from complaint_manager import ComplaintManager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CORS — restrict to live domain in production via ALLOWED_ORIGINS env var
# ---------------------------------------------------------------------------
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS: list = [o.strip() for o in _raw_origins.split(",") if o.strip()] or ["*"]

app = FastAPI(
    title="AI Smart Civic Services API",
    description="Citizens report local problems; AI classifies, prioritizes, and summarizes them.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Dependency initialization (singletons)
# ---------------------------------------------------------------------------
db = DatabaseManager()
ai = AIAnalyzer()
manager = ComplaintManager(db=db, ai=ai)

# ---------------------------------------------------------------------------
# Authentication Configuration
# ---------------------------------------------------------------------------
_DEFAULT_SECRET = "civicai-default-secret-key"
SECRET_KEY      = os.environ.get("SECRET_KEY", _DEFAULT_SECRET)
ALGORITHM      = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

if SECRET_KEY == _DEFAULT_SECRET:
    logger.warning(
        "⚠️  Using default SECRET_KEY — set a strong SECRET_KEY env var in production!"
    )

ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL", "admin@civicai.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# Auto-derive Google redirect URI from APP_URL when deployed
_APP_URL = os.environ.get("APP_URL", "").rstrip("/")
GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    f"{_APP_URL}/api/auth/google/callback" if _APP_URL else "http://localhost:8000/api/auth/google/callback"
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_jwt_token(data: dict, expires_hours: float = ACCESS_TOKEN_EXPIRE_HOURS) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=expires_hours)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_jwt_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user_from_cookie(access_token: Optional[str] = Cookie(default=None)) -> Optional[User]:
    """Extract and validate user from HTTP-only cookie."""
    if not access_token:
        return None
    payload = decode_jwt_token(access_token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.get_user_by_id(int(user_id))


def require_admin_cookie(access_token: Optional[str] = Cookie(default=None)) -> User:
    """Dependency: raises 401 if no valid admin cookie."""
    user = get_current_user_from_cookie(access_token)
    if not user or user.role != UserRole.ADMIN:
        raise HTTPException(status_code=401, detail="Admin authentication required.")
    return user


def verify_admin_token(authorization: str = "") -> bool:
    """Validate Bearer token from Authorization header (for JS API calls)."""
    if not authorization.startswith("Bearer "):
        return False
    token = authorization[7:]
    payload = decode_jwt_token(token)
    if not payload:
        return False
    user_id = payload.get("sub")
    role    = payload.get("role", "")
    if not user_id or role != "admin":
        return False
    return True


def _ensure_default_admin():
    """Create the default admin account if it doesn't exist."""
    existing = db.get_user_by_email(ADMIN_EMAIL)
    if not existing:
        admin = User(
            email=ADMIN_EMAIL,
            display_name="Admin",
            role=UserRole.ADMIN,
            password_hash=hash_password(ADMIN_PASSWORD),
        )
        db.create_user(admin)
        logger.info(f"Default admin account created: {ADMIN_EMAIL}")


_ensure_default_admin()

# ---------------------------------------------------------------------------
# Pydantic request/response schemas
# ---------------------------------------------------------------------------

class SubmitComplaintRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=2000,
                              description="Detailed description of the civic issue")
    location: str    = Field(..., min_length=2, max_length=300,
                              description="Street address, landmark, or area name")
    contact: str     = Field("", max_length=200,
                              description="Optional: email or phone number")

class UpdateComplaintRequest(BaseModel):
    status:      Optional[str] = None
    department:  Optional[str] = None
    admin_notes: Optional[str] = Field(None, max_length=1000)

class SignupRequest(BaseModel):
    email:        str = Field(..., min_length=3, max_length=200)
    password:     str = Field(..., min_length=6, max_length=200)
    display_name: str = Field(..., min_length=1, max_length=100)

class LoginRequest(BaseModel):
    email:    str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=1, max_length=200)

# ---------------------------------------------------------------------------
# Routes — Authentication
# ---------------------------------------------------------------------------

@app.post("/api/auth/signup", summary="Create a new citizen account")
def signup(body: SignupRequest, response: Response):
    """Register a new citizen user with email and password."""
    existing = db.get_user_by_email(body.email.lower())
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(
        email=body.email.lower(),
        display_name=body.display_name,
        role=UserRole.CITIZEN,
        password_hash=hash_password(body.password),
    )
    user = db.create_user(user)
    token = create_jwt_token({"sub": str(user.id), "role": user.role.value, "email": user.email})
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=86400 * 7, samesite="lax")
    logger.info(f"New citizen signup: {user.email}")
    return {"success": True, "user": user.to_dict(), "token": token}


@app.post("/api/auth/login", summary="Login with email and password")
def login(body: LoginRequest, response: Response):
    """Authenticate a user and return a JWT token."""
    user = db.get_user_by_email(body.email.lower())
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_jwt_token({"sub": str(user.id), "role": user.role.value, "email": user.email})
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=86400 * 7, samesite="lax")
    logger.info(f"User login: {user.email} [{user.role.value}]")
    return {"success": True, "user": user.to_dict(), "token": token}


@app.post("/api/auth/logout", summary="Logout and clear session cookie")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"success": True}


@app.get("/api/auth/me", summary="Get current user profile")
def get_me(access_token: Optional[str] = Cookie(default=None)):
    user = get_current_user_from_cookie(access_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return {"success": True, "user": user.to_dict()}


@app.get("/api/auth/token", summary="Get JWT from session cookie (for JS API calls)")
def get_token_from_cookie(access_token: Optional[str] = Cookie(default=None)):
    """Returns the JWT token if a valid session cookie exists."""
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    payload = decode_jwt_token(access_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    user = db.get_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return {"success": True, "token": access_token, "user": user.to_dict()}


# ── Google OAuth ────────────────────────────────────────────────────────────

@app.get("/api/auth/google/login", summary="Initiate Google OAuth login")
def google_login():
    """Redirect user to Google OAuth consent screen."""
    import urllib.parse
    if not GOOGLE_CLIENT_ID:
        # Fallback to Mock Auth if no client ID is provided
        params = urllib.parse.urlencode({"code": "mock_google_oauth_code"})
        return RedirectResponse(f"/api/auth/google/callback?{params}")
        
    params = urllib.parse.urlencode({
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "access_type":   "offline",
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@app.get("/api/auth/google/callback", summary="Google OAuth callback")
async def google_callback(code: str, response: Response):
    """Exchange auth code for tokens, get user profile, create/login user."""
    try:
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or code == "mock_google_oauth_code":
            profile = {
                "id": "1234567890_mock",
                "email": "google.citizen@example.com",
                "name": "Google Test Citizen",
                "picture": "https://lh3.googleusercontent.com/a/default-user=s96-c"
            }
        else:
            async with httpx.AsyncClient() as client:
                # Exchange code for access token
                token_res = await client.post("https://oauth2.googleapis.com/token", data={
                    "code":          code,
                    "client_id":     GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri":  GOOGLE_REDIRECT_URI,
                    "grant_type":    "authorization_code",
                })
                token_data = token_res.json()
                # Get user profile from Google
                profile_res = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {token_data['access_token']}"},
                )
                profile = profile_res.json()

        google_id   = profile["id"]
        email       = profile["email"].lower()
        name        = profile.get("name", email.split("@")[0])
        avatar      = profile.get("picture", "")

        # Look up or create user
        user = db.get_user_by_google_id(google_id)
        if not user:
            user = db.get_user_by_email(email)
            if user:
                # Link Google ID to existing email account
                with db._get_connection() as conn:
                    conn.execute("UPDATE users SET google_id=?, avatar_url=? WHERE id=?",
                                 (google_id, avatar, user.id))
                    conn.commit()
            else:
                # Brand new user via Google
                user = User(email=email, display_name=name, google_id=google_id,
                            avatar_url=avatar, role=UserRole.CITIZEN)
                user = db.create_user(user)

        token = create_jwt_token({"sub": str(user.id), "role": user.role.value, "email": user.email})
        logger.info(f"Google OAuth login: {email}")
        redirect_url = "/login?oauth=success"
        if user.role == UserRole.ADMIN:
            redirect_url += "&redirect=admin"
        
        # Set the cookie directly on the returned RedirectResponse object
        redirect_response = RedirectResponse(url=redirect_url, status_code=302)
        redirect_response.set_cookie(key="access_token", value=token, httponly=True, max_age=86400 * 7, samesite="lax")
        return redirect_response
    except Exception as e:
        logger.error(f"Google OAuth error: {e}")
        return RedirectResponse(url="/login?error=google_auth_failed", status_code=302)


@app.post("/api/admin/reset-db", summary="Purge all complaints (admin only)")
def reset_database(authorization: str = Header(default="")):
    """Deletes ALL complaint records from the database. Requires admin auth."""
    if not verify_admin_token(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized. Please log in.")
    try:
        with db._get_connection() as conn:
            conn.execute("DELETE FROM complaints")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='complaints'")
            conn.commit()
        logger.info("Database reset: all complaints purged by admin.")
        return {"success": True, "message": "All complaint records have been purged."}
    except Exception as e:
        logger.error(f"reset_database error: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset database.")

# ---------------------------------------------------------------------------
# Routes — Citizen
# ---------------------------------------------------------------------------

@app.post("/api/complaints", status_code=201, summary="Submit a new complaint")
def submit_complaint(body: SubmitComplaintRequest):
    """
    Accepts a citizen complaint, runs AI analysis, saves to database.
    Returns the full complaint object including AI-generated fields.
    """
    try:
        complaint = manager.submit_complaint(
            description=body.description,
            location=body.location,
            contact=body.contact,
        )
        return {"success": True, "complaint": complaint.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"submit_complaint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process complaint. Please try again.")

# ---------------------------------------------------------------------------
# Routes — Admin / Shared
# ---------------------------------------------------------------------------

@app.get("/api/complaints/export/csv", summary="Export all complaints as CSV")
def export_complaints_csv(authorization: str = Header(default="")):
    """Admin-only: download all complaints as a CSV file."""
    if not verify_admin_token(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized. Admin login required.")
    import csv, io
    from fastapi.responses import StreamingResponse
    complaints = manager.list_complaints(limit=10000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID","Description","Location","Contact","Category","Priority",
                     "Status","Department","AI Summary","AI Confidence","AI Fallback",
                     "Admin Notes","Date Submitted","Date Resolved"])
    for c in complaints:
        writer.writerow([c.id,c.description,c.location,c.contact,
                         c.category.value,c.priority.value,c.status.value,c.department.value,
                         c.ai_summary,round(c.ai_confidence,2),c.ai_used_fallback,
                         c.admin_notes,c.date_submitted.isoformat(),
                         c.date_resolved.isoformat() if c.date_resolved else ""])
    output.seek(0)
    fname = f"civic_complaints_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(iter([output.getvalue()]),media_type="text/csv",
                             headers={"Content-Disposition":f"attachment; filename={fname}"})


@app.get("/api/complaints", summary="List complaints with optional filters")
def list_complaints(
    status:   Optional[str] = Query(None, description="Filter by status"),
    category: Optional[str] = Query(None, description="Filter by category"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    search:   Optional[str] = Query(None, description="Free-text search"),
    limit:    int            = Query(100, ge=1, le=500),
    offset:   int            = Query(0,   ge=0),
):
    complaints = manager.list_complaints(
        status=status, category=category, priority=priority,
        search=search, limit=limit, offset=offset,
    )
    return {
        "success": True,
        "count": len(complaints),
        "complaints": [c.to_dict() for c in complaints],
    }


@app.get("/api/complaints/{complaint_id}", summary="Get a single complaint by ID")
def get_complaint(complaint_id: int):
    complaint = manager.get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail=f"Complaint #{complaint_id} not found.")
    return {"success": True, "complaint": complaint.to_dict()}


@app.patch("/api/complaints/{complaint_id}", summary="Update complaint status / department")
def update_complaint(complaint_id: int, body: UpdateComplaintRequest, authorization: str = Header(default="")):
    if not verify_admin_token(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized. Admin login required.")
    # Validate enum values if provided
    if body.status and body.status not in [s.value for s in ComplaintStatus]:
        raise HTTPException(status_code=422, detail=f"Invalid status: {body.status}")
    if body.department and body.department not in [d.value for d in Department]:
        raise HTTPException(status_code=422, detail=f"Invalid department: {body.department}")

    updated = manager.update_complaint(
        complaint_id=complaint_id,
        status=body.status,
        department=body.department,
        admin_notes=body.admin_notes,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Complaint #{complaint_id} not found.")
    return {"success": True, "complaint": updated.to_dict()}


@app.get("/api/statistics", summary="Dashboard statistics")
def get_statistics():
    stats = manager.get_statistics()
    return {"success": True, "statistics": stats}


@app.get("/api/meta", summary="API metadata — enum values for frontend")
def get_meta():
    """Returns all valid enum values so the frontend never hardcodes them."""
    return {
        "categories":  [c.value for c in Category],
        "priorities":  [p.value for p in Priority],
        "statuses":    [s.value for s in ComplaintStatus],
        "departments": [d.value for d in Department],
        "ai_active":   ai.is_using_ai,
        "google_oauth_enabled": True, # Always true so users can click it and use mock flow if credentials not set
    }


@app.get("/api/health", summary="Health check")
def health_check():
    return {"status": "ok", "ai_active": ai.is_using_ai}



@app.get("/api/complaints/{complaint_id}/suggest-action", summary="AI-suggested next action for admins")
async def suggest_action(complaint_id: int):
    """
    Advanced AI feature: analyzes a complaint and suggests the optimal next action
    for the admin — e.g. which department to assign, what action to take, urgency level.
    """
    complaint = manager.get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail=f"Complaint #{complaint_id} not found.")

    if not ai.is_using_ai:
        return {
            "success": True,
            "suggestion": f"Assign to {complaint.department.value} and update status to In Progress.",
            "ai_active": False,
        }
    try:
        from google import genai
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
        prompt = f"""You are an expert civic operations advisor.
Analyze this complaint and give a concise, actionable recommendation for the admin.

Complaint:
  Category: {complaint.category.value}
  Priority: {complaint.priority.value}
  Status: {complaint.status.value}
  Department: {complaint.department.value}
  Location: {complaint.location}
  Description: {complaint.description}
  AI Summary: {complaint.ai_summary}
  Days Open: {(datetime.utcnow() - complaint.date_submitted).days}

Respond in 2-3 sentences: what should the admin do RIGHT NOW?"""
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return {"success": True, "suggestion": response.text.strip(), "ai_active": True}
    except Exception as e:
        logger.error(f"Suggest action error: {e}")
        raise HTTPException(status_code=500, detail="AI suggestion unavailable.")



class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    history: list = Field(default=[], description="Prior conversation turns")

class DuplicateCheckRequest(BaseModel):
    description: str = Field(..., min_length=10, max_length=2000)
    location: str = Field("", max_length=300)


@app.post("/api/chat", summary="AI civic assistant chat")
async def chat(body: ChatRequest):
    """
    Conversational AI assistant for citizens.
    Tries Gemini first; falls back to a rich rule-based civic assistant engine.
    """
    # Try Gemini API if available
    if ai.is_using_ai:
        try:
            from google import genai
            client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
            open_count = manager.db.get_complaint_count(status="Open")
            total = manager.db.get_complaint_count()
            system_prompt = f"""You are a helpful AI assistant for the AI Smart Civic Services platform.
Your role is to help citizens report local problems and understand how the system works.

Current system status:
- Total complaints in system: {total}
- Currently open complaints: {open_count}
- AI classification: Active (Gemini-powered)

Civic categories handled: Water/Drainage, Roads/Pavements, Waste/Sanitation,
Electricity, Parks/Green Spaces, Noise/Disturbance, Public Safety, Other.
Complaint lifecycle: Open → Assigned → In Progress → Resolved
Department SLA targets: Water Authority 12h, Electricity Board 24h, Public Works 48h, Waste Management 24h, Parks & Recreation 72h, Police 4h.

Always be friendly, helpful, and concise. If a citizen describes a problem, tell them
which category it falls under and encourage them to submit it using the form."""
            full_prompt = system_prompt + f"\n\nCitizen's message: {body.message}"
            response = client.models.generate_content(model="gemini-2.0-flash", contents=full_prompt)
            return {"success": True, "reply": response.text.strip(), "ai_active": True}
        except Exception as e:
            logger.warning(f"Chat Gemini call failed, using smart fallback: {e}")

    # ── Smart local fallback chatbot ──────────────────────────────────────
    return {"success": True, "reply": _smart_chat_fallback(body.message), "ai_active": False}


def _smart_chat_fallback(message: str) -> str:
    """Rule-based civic chatbot — works offline with no API key needed."""
    msg = message.lower().strip()

    # Greeting
    if any(w in msg for w in ["hello", "hi", "hey", "salam", "good morning", "good afternoon"]):
        return ("👋 Hello! I'm your CivicAI assistant. I can help you report local issues, "
                "understand how our complaint system works, and tell you which department handles your problem. "
                "What can I help you with today?")

    # Water/Drainage
    if any(w in msg for w in ["water", "pipe", "leak", "flood", "drain", "sewage", "burst", "tap", "overflow"]):
        return ("💧 **Water & Drainage issues** are handled by the **Water Authority** with a **12-hour SLA** "
                "for critical problems like burst pipes.\n\n"
                "Please submit your report using the form above. Include your exact location and describe "
                "the severity. Critical water issues (burst mains, flooding) receive immediate dispatch.")

    # Roads/Potholes
    if any(w in msg for w in ["road", "pothole", "pavement", "sidewalk", "crack", "bridge", "traffic", "tarmac"]):
        return ("🛣️ **Road & Pavement issues** are managed by **Public Works Department** with a **48-hour response SLA**.\n\n"
                "To report: describe the size and danger level of the defect, and include the exact street name or landmark. "
                "Dangerous potholes causing vehicle damage are elevated to High priority.")

    # Waste/Garbage
    if any(w in msg for w in ["garbage", "waste", "rubbish", "trash", "bin", "litter", "dump", "smell", "odour"]):
        return ("🗑️ **Waste & Sanitation** is managed by the **Waste Management Department** with a **24-hour SLA**.\n\n"
                "For uncollected bins, illegal dumping, or sanitation hazards — submit your report with the address and "
                "our field crews will be dispatched for cleanup.")

    # Electricity
    if any(w in msg for w in ["electricity", "power", "light", "streetlight", "wire", "electric", "outage", "blackout"]):
        return ("⚡ **Electricity issues** are handled by the **Electricity Board** with a **24-hour SLA**.\n\n"
                "For sparking wires or live cables — this is a **Critical** safety hazard. "
                "Please call emergency services AND submit a report. Our AI will escalate it immediately.")

    # Parks/Green
    if any(w in msg for w in ["park", "tree", "grass", "garden", "playground", "bench", "green"]):
        return ("🌳 **Parks & Green Spaces** are managed by **Parks & Recreation** with a **72-hour SLA**.\n\n"
                "Issues like broken equipment, fallen trees, or overgrown areas can be reported via the form. "
                "Hazardous tree branches are elevated to High priority.")

    # Noise
    if any(w in msg for w in ["noise", "loud", "music", "construction", "disturb", "night", "party"]):
        return ("🔊 **Noise & Disturbance** reports go to the **Noise Control Division** with a **24-hour SLA**.\n\n"
                "Include the time of disturbance, type of noise, and the address. Late-night construction violations "
                "receive priority enforcement.")

    # Safety/Crime
    if any(w in msg for w in ["safety", "crime", "robbery", "theft", "dangerous", "fight", "threat", "assault", "police"]):
        return ("🚨 **Public Safety** issues are routed to the **Police Department** with a **4-hour SLA** — the fastest "
                "response in our system.\n\n"
                "For emergencies, **call 999 immediately**. For non-emergency safety concerns, submit your report "
                "here and our system will flag it as Critical priority.")

    # How to report
    if any(w in msg for w in ["how", "report", "submit", "complaint", "file", "raise"]):
        return ("📝 **How to report an issue:**\n\n"
                "1. Describe your problem in the text box (be as specific as possible)\n"
                "2. Enter the location or landmark\n"
                "3. Optionally add your contact details for status updates\n"
                "4. Click **Submit Civic Report** — our AI will classify, prioritize and dispatch automatically!\n\n"
                "Your report is processed in seconds and routed to the right city department.")

    # Status tracking
    if any(w in msg for w in ["status", "track", "follow", "update", "when", "resolve", "progress"]):
        return ("📊 **Complaint lifecycle:**\n\n"
                "🔵 **Open** → Report received and awaiting assignment\n"
                "🟣 **Assigned** → Department notified, field crew scheduled\n"
                "🔷 **In Progress** → Active repair/resolution underway\n"
                "✅ **Resolved** → Issue fixed and verified\n\n"
                "Check the **Live Community Feed** at the bottom of the page to see recent report statuses.")

    # SLA/timing
    if any(w in msg for w in ["time", "long", "sla", "hours", "days", "fast", "slow", "response", "when"]):
        return ("⏱️ **Department Response Time Targets (SLA):**\n\n"
                "🚰 Water Authority — **12 hours** (burst pipes, flooding)\n"
                "⚡ Electricity Board — **24 hours** (outages, streetlights)\n"
                "🛣️ Public Works — **48 hours** (roads, potholes)\n"
                "🗑️ Waste Management — **24 hours** (garbage, sanitation)\n"
                "🌳 Parks & Recreation — **72 hours** (parks, green spaces)\n"
                "🚨 Police — **4 hours** (public safety)\n\n"
                "Critical issues always receive expedited response regardless of category.")

    # Thank you
    if any(w in msg for w in ["thank", "terima kasih", "thanks", "great", "good"]):
        return "😊 You're welcome! Feel free to ask anything else or go ahead and submit your report. Together we build a better city! 🏙️"

    # Default helpful response
    return ("🤖 I'm your CivicAI assistant. I can help with:\n\n"
            "• **Reporting issues** — water, roads, electricity, waste, safety, parks, noise\n"
            "• **Understanding SLA times** — how quickly each department responds\n"
            "• **Complaint lifecycle** — tracking your issue from submission to resolution\n"
            "• **How to use this portal** — tips for effective reporting\n\n"
            "Just describe your civic issue and I'll point you to the right department! 🏙️")


@app.post("/api/complaints/check-duplicate", summary="Check for duplicate complaints")
async def check_duplicate(body: DuplicateCheckRequest):
    """
    Advanced AI feature: detects if a semantically similar complaint already exists
    in the database to prevent duplicate submissions.
    """
    existing = manager.list_complaints(limit=100)
    if not existing:
        return {"is_duplicate": False, "similar_complaint": None, "similarity_score": 0.0}

    # Build summary for AI comparison
    existing_summaries = "\n".join(
        f"ID {c.id}: [{c.category.value}] {c.location} — {c.description[:120]}"
        for c in existing[:30]  # check most recent 30
    )

    if not ai.is_using_ai:
        # Keyword fallback: simple location+category overlap check
        new_lower = body.description.lower()
        for c in existing:
            if c.location.lower() in body.location.lower() or body.location.lower() in c.location.lower():
                overlap = sum(1 for w in c.description.lower().split() if w in new_lower and len(w) > 4)
                if overlap >= 3:
                    return {"is_duplicate": True, "similar_complaint": c.to_dict(), "similarity_score": 0.75}
        return {"is_duplicate": False, "similar_complaint": None, "similarity_score": 0.0}

    try:
        from google import genai
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
        prompt = f"""You are a duplicate detection AI for a civic complaints system.
New complaint:
  Description: "{body.description}"
  Location: "{body.location}"

Existing complaints:
{existing_summaries}

Respond ONLY with valid JSON:
{{"is_duplicate": true/false, "most_similar_id": <int or null>, "similarity_score": <0.0-1.0>, "reason": "<brief explanation>"}}

Mark as duplicate only if the same issue at essentially the same location is already reported and not yet resolved."""

        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        import json, re
        match = re.search(r"\{.*\}", response.text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            similar = None
            if result.get("is_duplicate") and result.get("most_similar_id"):
                similar = manager.get_complaint(int(result["most_similar_id"]))
            return {
                "is_duplicate": result.get("is_duplicate", False),
                "similar_complaint": similar.to_dict() if similar else None,
                "similarity_score": result.get("similarity_score", 0.0),
                "reason": result.get("reason", ""),
            }
    except Exception as e:
        logger.error(f"Duplicate check error: {e}")
    return {"is_duplicate": False, "similar_complaint": None, "similarity_score": 0.0}


@app.get("/api/complaints/{complaint_id}/suggest-action", summary="AI-suggested next action for admins")
async def suggest_action(complaint_id: int):
    """
    Advanced AI feature: analyzes a complaint and suggests the optimal next action
    for the admin — e.g. which department to assign, what action to take, urgency level.
    """
    complaint = manager.get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail=f"Complaint #{complaint_id} not found.")

    if not ai.is_using_ai:
        return {
            "success": True,
            "suggestion": f"Assign to {complaint.department.value} and update status to In Progress.",
            "ai_active": False,
        }
    try:
        from google import genai
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
        prompt = f"""You are an expert civic operations advisor.
Analyze this complaint and give a concise, actionable recommendation for the admin.

Complaint:
  Category: {complaint.category.value}
  Priority: {complaint.priority.value}
  Status: {complaint.status.value}
  Department: {complaint.department.value}
  Location: {complaint.location}
  Description: {complaint.description}
  AI Summary: {complaint.ai_summary}
  Days Open: {((__import__('datetime').datetime.utcnow()) - complaint.date_submitted).days}

Respond in 2–3 sentences: what should the admin do RIGHT NOW?"""
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return {"success": True, "suggestion": response.text.strip(), "ai_active": True}
    except Exception as e:
        logger.error(f"Suggest action error: {e}")
        raise HTTPException(status_code=500, detail="AI suggestion unavailable.")



frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

if os.path.isdir(frontend_dir):
    def _serve(filename: str):
        return FileResponse(os.path.join(frontend_dir, filename))

    @app.get("/static/{filename}", include_in_schema=False)
    def serve_static_css(filename: str):
        path = os.path.join(frontend_dir, "css", filename)
        if os.path.isfile(path):
            return FileResponse(path)
        raise HTTPException(status_code=404, detail="Static file not found")

    @app.get("/css/{filename}", include_in_schema=False)
    def serve_css(filename: str):
        path = os.path.join(frontend_dir, "css", filename)
        if os.path.isfile(path):
            return FileResponse(path)
        raise HTTPException(status_code=404, detail="CSS file not found")

    @app.get("/js/{filename}", include_in_schema=False)
    def serve_js(filename: str):
        path = os.path.join(frontend_dir, "js", filename)
        if os.path.isfile(path):
            return FileResponse(path)
        raise HTTPException(status_code=404, detail="JS file not found")

    @app.get("/images/{filename}", include_in_schema=False)
    def serve_images(filename: str):
        path = os.path.join(frontend_dir, "images", filename)
        if os.path.isfile(path):
            return FileResponse(path)
        raise HTTPException(status_code=404, detail="Image not found")

    @app.get("/frontend/{subpath:path}", include_in_schema=False)
    def serve_frontend_subpath(subpath: str):
        path = os.path.join(frontend_dir, subpath)
        if os.path.isfile(path):
            return FileResponse(path)
        raise HTTPException(status_code=404, detail="File not found")

    @app.get("/", include_in_schema=False)
    def serve_home():
        return _serve("index.html")

    @app.get("/report", include_in_schema=False)
    def serve_report():
        return _serve("report.html")

    @app.get("/feed", include_in_schema=False)
    def serve_feed():
        return _serve("feed.html")

    @app.get("/login", include_in_schema=False)
    def serve_login():
        return _serve("login.html")

    @app.get("/admin", include_in_schema=False)
    def serve_admin(access_token: Optional[str] = Cookie(default=None)):
        """Serve the admin dashboard only if the user has a valid admin token."""
        user = get_current_user_from_cookie(access_token)
        if not user or user.role != UserRole.ADMIN:
            return RedirectResponse(url="/login?redirect=admin&reason=admin_required", status_code=302)
        return _serve("admin.html")


# ---------------------------------------------------------------------------
# Dev runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
