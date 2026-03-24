from __future__ import annotations

from typing import Iterable

from sqlalchemy import select

from bot.database import Level, SessionLocal


def add_level(price: float, label: str = "", direction: str = "both") -> Level:
    with SessionLocal() as session:
        level = Level(price=price, label=label, direction=direction)
        session.add(level)
        session.commit()
        session.refresh(level)
        return level


def list_active_levels() -> Iterable[Level]:
    with SessionLocal() as session:
        stmt = select(Level).where(Level.active.is_(True)).order_by(Level.price.asc())
        return list(session.scalars(stmt))


def deactivate_level(level_id: int) -> bool:
    with SessionLocal() as session:
        level = session.get(Level, level_id)
        if not level:
            return False
        level.active = False
        session.commit()
        return True
