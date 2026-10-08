"""SQLAlchemy models for airdrop data."""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Integer, Float, Text, DateTime, JSON, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Airdrop(Base):
    """Main airdrop entity stored in the database."""

    __tablename__ = "airdrops"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    airdrop_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    chain: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    contract_address: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)

    # Scoring
    legitimacy_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    score_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    reasons: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    risk_label: Mapped[str] = mapped_column(String(32), default="Unknown", index=True)
    red_flags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Participation strategy (for Streamlit checkboxes)
    # zero_tx | low_tx | medium_tx | high_tx
    participation_level: Mapped[str] = mapped_column(
        String(32), default="medium_tx", index=True
    )
    participation_tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Sources & status
    sources: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    source_links: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="new", index=True
    )  # new / notified / done / ignored / scam

    # Metadata
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_scanned: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Extra data from APIs
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_airdrops_score_status", "legitimacy_score", "status"),
        Index("ix_airdrops_participation", "participation_level"),
    )

    def __repr__(self) -> str:
        return (
            f"<Airdrop(id={self.id}, name={self.name}, "
            f"score={self.legitimacy_score}, level={self.participation_level})>"
        )


class ScanLog(Base):
    """Log of each scan run for monitoring."""

    __tablename__ = "scan_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    airdrops_found: Mapped[int] = mapped_column(Integer, default=0)
    airdrops_new: Mapped[int] = mapped_column(Integer, default=0)
    airdrops_updated: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")

    def __repr__(self) -> str:
        return f"<ScanLog(id={self.id}, status={self.status})>"
