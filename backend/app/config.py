"""
ShadowPrompt Configuration
Centralized settings for the ShadowScan MVP.
All scoring weights, security limits, and detection rules are configurable here.
"""

from pydantic_settings import BaseSettings
from typing import List, Set
import ipaddress


class Settings(BaseSettings):
    """Application settings loaded from environment variables or defaults."""

    # --- Application ---
    APP_NAME: str = "ShadowPrompt"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- External APIs ---
    ANTHROPIC_API_KEY: str = ""

    # --- Local LLM Support (Ollama / LM Studio) ---
    ALLOW_LOCAL_LLM: bool = True  # Allow connections to localhost LLM servers
    LOCAL_LLM_ALLOWED_PORTS: List[int] = [11434, 1234, 8080]  # Ollama, LM Studio, text-gen-webui

    # --- Database ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./shadowprompt.db"

    # --- URL Fetching & SSRF Protection ---
    MAX_URL_RESPONSE_SIZE: int = 5 * 1024 * 1024  # 5MB
    URL_TIMEOUT: int = 10  # seconds
    MAX_REDIRECTS: int = 3
    ALLOWED_SCHEMES: List[str] = ["http", "https"]

    # --- File Upload ---
    MAX_UPLOAD_SIZE: int = 2 * 1024 * 1024  # 2MB
    ALLOWED_EXTENSIONS: List[str] = [".html", ".htm"]

    # --- Rate Limiting ---
    SCAN_RATE_LIMIT: int = 30  # scans per minute per IP

    # --- Scoring Weights (source location) ---
    WEIGHT_VISIBLE_TEXT: int = 10
    WEIGHT_HTML_COMMENT: int = 20
    WEIGHT_META_TAG: int = 20
    WEIGHT_IMAGE_ALT: int = 20
    WEIGHT_ARIA_LABEL: int = 20
    WEIGHT_TITLE_ATTR: int = 15
    WEIGHT_DATA_ATTR: int = 15
    WEIGHT_HIDDEN_ELEMENT: int = 25
    WEIGHT_SCRIPT_CONTENT: int = 20
    WEIGHT_INLINE_STYLE: int = 15
    WEIGHT_LINK_BUTTON: int = 10
    WEIGHT_NOSCRIPT: int = 15

    # --- Scoring Weights (category severity) ---
    WEIGHT_INSTRUCTION_OVERRIDE: float = 1.5
    WEIGHT_DATA_EXFILTRATION: float = 2.0
    WEIGHT_UNAUTHORIZED_ACTION: float = 1.3
    WEIGHT_PERSONA_OVERRIDE: float = 1.2
    WEIGHT_STEALTH_INSTRUCTION: float = 1.4
    WEIGHT_CONTEXT_INJECTION: float = 1.3
    WEIGHT_CHAINED_PAYLOAD: float = 1.1

    # --- Scoring Bonus ---
    BONUS_PER_ADDITIONAL_SOURCE: int = 10  # bonus for each unique source after the first

    # --- Severity Thresholds ---
    SEVERITY_CLEAN_MAX: int = 20
    SEVERITY_LOW_MAX: int = 40
    SEVERITY_MEDIUM_MAX: int = 60
    SEVERITY_HIGH_MAX: int = 80
    # Above HIGH_MAX = Critical

    model_config = {"env_prefix": "SP_", "env_file": ".env"}


# Blocked IP ranges for SSRF prevention
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("10.0.0.0/8"),         # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),      # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),     # Private Class C
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local
    ipaddress.ip_network("0.0.0.0/8"),          # Current network
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]


# Source location weight mapping
SOURCE_WEIGHTS = {
    "HTML Comment": 20,
    "Meta Tag": 20,
    "Image Alt Text": 20,
    "ARIA Label": 20,
    "Title Attribute": 15,
    "Data Attribute": 15,
    "Hidden Element": 25,
    "Visible Text": 10,
    "Script Content": 20,
    "Inline Style": 15,
    "Link/Button Text": 10,
    "Noscript Block": 15,
}

# Category severity multiplier mapping
CATEGORY_MULTIPLIERS = {
    "Instruction Override": 1.5,
    "Data Exfiltration": 2.0,
    "Unauthorized Action": 1.3,
    "Persona/Role Override": 1.2,
    "Stealth Instruction": 1.4,
    "Context Injection": 1.3,
    "Chained Payload Setup": 1.1,
}


settings = Settings()
