"""
Account credential storage and selection.

Stores multiple provider accounts (email/password) and supports selection + rotation.
Formerly ECE (Experimental Credential Engine), now renamed as it replaced the old system entirely.
"""

from .manager import EceManager
from .models import CredentialPair

__all__ = [
    "CredentialPair",
    "EceManager",
]
