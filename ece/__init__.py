"""
Experimental Credential Engine (ECE).

ECE is an opt-in alternative credential storage/selection system that can run
alongside the legacy per-provider single credential fields.
"""

from .manager import EceManager
from .models import CredentialPair

__all__ = [
    "CredentialPair",
    "EceManager",
]

