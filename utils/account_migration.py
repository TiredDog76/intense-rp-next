from __future__ import annotations

from typing import Any, Iterable, Optional

from drivers.providers import DriverProvider
from ece.manager import EceManager
from ece.models import CredentialPair
from utils.logger import Logger


_LEGACY_IMPORT_FLAG_KEY = "accounts.legacy_credentials_imported"
_LEGACY_IMPORT_FLAG_KEY_COMPAT = "ece.legacy_credentials_imported"


def _read_legacy_pair(config_manager: Any, email_key: str, password_key: str) -> Optional[CredentialPair]:
    try:
        email = str(config_manager.get_setting("providers_credentials", email_key) or "").strip()
        password = str(config_manager.get_setting("providers_credentials", password_key) or "")
    except Exception:
        return None

    if not email or not password:
        return None
    return CredentialPair(email=email, password=password)


def _providers_with_legacy_fields() -> Iterable[tuple[DriverProvider, str, str]]:
    return (
        (DriverProvider.DEEPSEEK, "deepseek_email", "deepseek_password"),
        (DriverProvider.GLM_CHAT, "glm_email", "glm_password"),
        (DriverProvider.MOONSHOT, "moonshot_email", "moonshot_password"),
    )


def migrate_legacy_credentials_to_accounts(config_manager: Any) -> bool:
    """
    Best-effort migration: import old per-provider credential fields into Credential Manager.

    This is safe to run multiple times. It only imports for a provider when:
    - legacy email+password exist, and
    - Credential Manager has no saved accounts for that provider yet.

    Returns True when at least one provider was imported successfully.
    """
    app_flags = getattr(config_manager, "app_flags", None)
    if app_flags is not None:
        try:
            if bool(app_flags.get_bool(_LEGACY_IMPORT_FLAG_KEY_COMPAT, default=False)) and not bool(
                app_flags.get_bool(_LEGACY_IMPORT_FLAG_KEY, default=False)
            ):
                app_flags.set(_LEGACY_IMPORT_FLAG_KEY, True)
        except Exception:
            pass

    config_dir = getattr(config_manager, "config_dir", None) or "config_data"
    mgr = EceManager(config_dir)

    imported_any = False
    for provider, email_key, password_key in _providers_with_legacy_fields():
        try:
            existing = mgr.get_provider_pairs(provider)
        except Exception:
            existing = []

        if existing:
            continue

        legacy_pair = _read_legacy_pair(config_manager, email_key, password_key)
        if legacy_pair is None:
            continue

        ok, errors = mgr.set_provider_pairs(provider, [legacy_pair])
        if ok:
            imported_any = True
            continue

        details = "; ".join(errors) if errors else "unknown error"
        Logger.warning(f"Legacy credential import: failed for {provider.value}: {details}")

    if imported_any:
        if app_flags is not None:
            try:
                app_flags.set(_LEGACY_IMPORT_FLAG_KEY, True)
            except Exception:
                pass

    return imported_any


def legacy_import_completed(config_manager: Any) -> bool:
    app_flags = getattr(config_manager, "app_flags", None)
    if app_flags is None:
        return False

    try:
        if bool(app_flags.get_bool(_LEGACY_IMPORT_FLAG_KEY, default=False)):
            return True
        if bool(app_flags.get_bool(_LEGACY_IMPORT_FLAG_KEY_COMPAT, default=False)):
            return True
    except Exception:
        return False

    return False
