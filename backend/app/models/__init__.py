"""Model package — re-exports the single Base (see base.py). Never redefine here."""
from .base import Base, TenantMixin

__all__ = ["Base", "TenantMixin"]
