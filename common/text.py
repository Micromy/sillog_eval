# common/text.py
"""문자열/데이터 변환 유틸."""
from typing import Optional


def truncate(value, max_bytes: int) -> Optional[str]:
    """VARCHAR2 컬럼용 - UTF-8 BYTE 기준 안전 절삭.

    - None/빈문자열/falsy → None
    - 비문자열 → str() 변환
    - BYTE 초과 시 문자 경계 안전하게 잘라 '...' 추가
    """
    if value is None:
        return None
    if not isinstance(value, str):
        if not value:
            return None
        value = str(value)
    if value == "":
        return None

    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value

    truncated_bytes = encoded[: max_bytes - 3]
    truncated = truncated_bytes.decode("utf-8", errors="ignore")
    return truncated + "..."


def clob_or_none(value) -> Optional[str]:
    """CLOB 컬럼용 - 길이 제한 없이 None/빈값만 None 변환."""
    if value is None:
        return None
    if not isinstance(value, str):
        if not value:
            return None
        value = str(value)
    if value == "":
        return None
    return value


def safe_dict(value) -> dict:
    """dict가 아니거나 None이면 빈 dict 반환."""
    if isinstance(value, dict):
        return value
    return {}


def safe_list(value) -> list:
    """list가 아니거나 None이면 빈 list 반환."""
    if isinstance(value, list):
        return value
    return []
