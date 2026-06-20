"""
ShadowPrompt Database Models
SQLAlchemy models for scan results and findings.
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
