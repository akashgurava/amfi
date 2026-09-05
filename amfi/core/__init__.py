"""Core interfaces and protocols for AMFI data and database models."""

from .base import (
    Buildable,
    DedupView,
    DerivedTable,
    DerivedView,
    RawTable,
    T,
    T_co,
    Table,
    View,
)

__all__ = [
    "Buildable",
    "DedupView",
    "DerivedTable",
    "DerivedView",
    "RawTable",
    "T",
    "T_co",
    "Table",
    "View",
]
