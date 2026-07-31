# config_gemini.py
# ==========================================
# AI / GEMINI (disabled for simple strategy)
# Set True to re-enable LLM validation when needed.
# ==========================================
import os
USE_GEMINI_AI = True
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_NEWS_MODEL = "gemini-3.5-flash"
GEMINI_NEWS_FALLBACK_MODEL = "gemini-flash-lite-latest"
