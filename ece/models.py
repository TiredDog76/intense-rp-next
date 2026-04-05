from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CredentialPair:
    email: str
    password: str
    pinned: bool = False
