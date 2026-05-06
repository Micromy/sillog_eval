# common/convert.py
"""데이터 변환 유틸."""
from typing import Any


def to_raw_dict(sillog_data: Any) -> dict:
    """SillogData(Pydantic) | dict → dict로 정규화.

    이미 dict면 그대로 반환, Pydantic v2(`model_dump`) / v1(`dict`) 메서드가 있으면 호출.
    어느 쪽도 아니면 TypeError.
    """
    if isinstance(sillog_data, dict):
        return sillog_data
    if hasattr(sillog_data, "model_dump"):
        return sillog_data.model_dump()
    if hasattr(sillog_data, "dict"):
        return sillog_data.dict()
    raise TypeError(f"sillog_data를 dict로 변환할 수 없음: {type(sillog_data)}")
