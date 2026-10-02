"""Declarative base for all ORM models.

A deterministic constraint naming convention is configured here so Alembic can
autogenerate reversible migrations -- without it, unnamed constraints cannot be
dropped cleanly on a downgrade.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(AsyncAttrs, DeclarativeBase):
    """Shared declarative base.

    ``AsyncAttrs`` exposes ``awaitable_attrs`` so lazy relationships can be
    loaded explicitly from async code instead of raising on implicit IO.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
