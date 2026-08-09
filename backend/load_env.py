"""
load_dotenv support — auto-loads .env file in development.
FastAPI main.py imports this at startup.
"""

from dotenv import load_dotenv
load_dotenv()
