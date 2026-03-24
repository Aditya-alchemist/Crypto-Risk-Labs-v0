from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from bot.config import settings


class Base(DeclarativeBase):
    pass


class Level(Base):
    __tablename__ = "levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(64), default="")
    price: Mapped[float] = mapped_column(Float, index=True)
    direction: Mapped[str] = mapped_column(String(8), default="both")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CrossEvent(Base):
    __tablename__ = "cross_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level_id: Mapped[int] = mapped_column(Integer, index=True)
    level_price: Mapped[float] = mapped_column(Float)
    touched_price: Mapped[float] = mapped_column(Float)
    crossed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TradeLog(Base):
    __tablename__ = "trade_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String(64), index=True)
    side: Mapped[str] = mapped_column(String(8))
    entry_price: Mapped[float] = mapped_column(Float)
    result: Mapped[str] = mapped_column(String(16), index=True)
    tp_hit: Mapped[str] = mapped_column(String(16), default="none")
    rr: Mapped[float] = mapped_column(Float, default=0.0)
    session_name: Mapped[str] = mapped_column(String(32), default="unknown")
    market_cycle: Mapped[str] = mapped_column(String(32), default="unknown")
    volatility: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PatternStat(Base):
    __tablename__ = "pattern_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String(64), unique=True)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
