"""
ShadowPrompt Database Models
SQLAlchemy models for scan results, findings, campaigns, and test results.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class ScanResult(Base):
    """Stores metadata and aggregate result for each ShadowScan scan."""
    __tablename__ = "scan_results"

    id = Column(String, primary_key=True, default=generate_uuid)
    target_url = Column(String, nullable=True)
    target_filename = Column(String, nullable=True)
    scan_type = Column(String, nullable=False)  # "url", "file", "demo"
    score = Column(Integer, nullable=False, default=0)
    severity = Column(String, nullable=False, default="Clean")
    finding_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    findings = relationship("Finding", back_populates="scan", cascade="all, delete-orphan")

    def __repr__(self):
        target = self.target_url or self.target_filename or "unknown"
        return f"<ScanResult(id={self.id}, target={target}, score={self.score})>"


class Finding(Base):
    """Stores individual findings within a scan."""
    __tablename__ = "findings"

    id = Column(String, primary_key=True, default=generate_uuid)
    scan_id = Column(String, ForeignKey("scan_results.id", ondelete="CASCADE"), nullable=False)
    source_location = Column(String, nullable=False)       # e.g., "HTML Comment", "Meta Tag"
    matched_rule = Column(String, nullable=False)           # The specific phrase/pattern matched
    matched_category = Column(String, nullable=False)       # e.g., "Instruction Override"
    evidence_text = Column(Text, nullable=False)            # The suspicious content (escaped)
    risk_weight = Column(Float, nullable=False, default=0)  # Contribution to total score
    impact = Column(Text, nullable=False)                   # Description of potential impact
    remediation = Column(Text, nullable=False)              # Recommended fix

    # Relationships
    scan = relationship("ScanResult", back_populates="findings")

    def __repr__(self):
        return f"<Finding(id={self.id}, category={self.matched_category}, source={self.source_location})>"


# =============================================================================
# Phase 2 — Lab Core Models
# =============================================================================

class Campaign(Base):
    """
    Stores metadata and results for an LLM security testing campaign.
    NOTE: API keys are NEVER stored here — only model name and base URL.
    """
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True, default=generate_uuid)
    model_name = Column(String, nullable=False)           # e.g., "gpt-4o-mini"
    base_url = Column(String, nullable=False)             # e.g., "https://api.openai.com/v1"
    selected_levels = Column(String, nullable=False)      # JSON list, e.g., "[1, 2, 3]"
    status = Column(String, nullable=False, default="running")  # "running", "completed", "failed", "cancelled"
    total_payloads = Column(Integer, nullable=False, default=0)
    completed_payloads = Column(Integer, nullable=False, default=0)
    pass_count = Column(Integer, nullable=False, default=0)
    fail_count = Column(Integer, nullable=False, default=0)
    partial_count = Column(Integer, nullable=False, default=0)
    unclear_count = Column(Integer, nullable=False, default=0)
    overall_score = Column(Float, nullable=True)          # 0.0 - 100.0
    overall_rating = Column(String, nullable=True)        # "Secure", "Moderate", "Vulnerable", "Critical"
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    test_results = relationship("TestResult", back_populates="campaign", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Campaign(id={self.id}, model={self.model_name}, status={self.status})>"


class TestResult(Base):
    """Stores the result of a single payload test within a campaign."""
    __tablename__ = "test_results"

    id = Column(String, primary_key=True, default=generate_uuid)
    campaign_id = Column(String, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    payload_id = Column(String, nullable=False)           # e.g., "L1_001"
    payload_name = Column(String, nullable=False)
    level = Column(Integer, nullable=False)
    category = Column(String, nullable=False)
    attack_prompt = Column(Text, nullable=False)          # The attack payload that was sent
    llm_response = Column(Text, nullable=False)           # Full LLM response text
    verdict = Column(String, nullable=False)              # "PASS", "FAIL", "PARTIAL", "UNCLEAR"
    evaluation_layer = Column(Integer, nullable=False)    # 1 or 2
    confidence = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Float, nullable=True)             # Response time in milliseconds
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    campaign = relationship("Campaign", back_populates="test_results")

    def __repr__(self):
        return f"<TestResult(id={self.id}, payload={self.payload_id}, verdict={self.verdict})>"

