"""
API Dependencies
================

Shared FastAPI dependencies for authentication, authorization, and
project lookup.
"""

from .auth import verify_auth
from .project import find_project

__all__ = ["verify_auth", "find_project"]
