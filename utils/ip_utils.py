from ipaddress import ip_address
from typing import Any, Iterable


def normalize_ip_address(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("IP address cannot be empty.")

    parsed = ip_address(text)
    mapped = getattr(parsed, "ipv4_mapped", None)
    if mapped is not None:
        parsed = mapped

    return parsed.compressed


def normalize_ip_list(values: Iterable[Any] | None) -> list[str]:
    normalized: list[str] = []
    for raw_value in (values or []):
        text = str(raw_value or "").strip()
        if not text:
            continue
        normalized.append(normalize_ip_address(text))
    return normalized


def is_ip_address_allowed(client_host: Any, allowed_values: Iterable[Any] | None) -> bool:
    try:
        client_ip = ip_address(str(client_host or "").strip())
    except ValueError:
        return False

    mapped = getattr(client_ip, "ipv4_mapped", None)
    if mapped is not None:
        client_ip = mapped

    for raw_value in (allowed_values or []):
        try:
            allowed_ip = ip_address(normalize_ip_address(raw_value))
        except ValueError:
            continue
        if client_ip == allowed_ip:
            return True
        if client_ip.is_loopback and allowed_ip.is_loopback:
            return True

    return False
