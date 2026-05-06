from pydantic import BaseModel, model_validator, field_validator
from typing import List, Optional, get_args, get_origin
import inspect


def make_fill_nulls():
    @model_validator(mode="before")
    @classmethod
    def fill_nulls(cls, v):
        if not isinstance(v, dict):
            return v
        hints = cls.__annotations__
        result = {}
        for k, val in v.items():
            # None이거나 빈 문자열인 경우 모두 처리
            is_empty = val is None or val == ""
            if is_empty and k in hints:
                hint = hints[k]
                args = get_args(hint)
                inner = args[0] if args else hint
                inner_origin = get_origin(inner)
                if inner_origin is list:
                    result[k] = []
                elif inspect.isclass(inner) and issubclass(inner, BaseModel):
                    result[k] = None  # 중첩 모델은 None 유지
                else:
                    result[k] = ""   # str 등은 "" 유지
            else:
                result[k] = val
        return result
    return fill_nulls


class Manager(BaseModel):
    role: Optional[str] = None
    role_type: Optional[str] = None
    job_category: Optional[str] = None
    fill_nulls = make_fill_nulls()


class InputData(BaseModel):
    file_name: Optional[str] = None
    file_format: Optional[str] = None
    file_path: Optional[str] = None
    description: Optional[str] = None
    task_link: Optional[str] = None
    managers: Optional[List[Manager]] = None
    fill_nulls = make_fill_nulls()


class Description(BaseModel):
    purpose: Optional[str] = None
    input_data: Optional[List[InputData]] = None
    task_manager: Optional[Manager] = None
    task_execution_method: Optional[str] = None
    tool: Optional[str] = None
    fill_nulls = make_fill_nulls()


class Output(BaseModel):
    file_name: Optional[str] = None
    file_format: Optional[str] = None
    file_path: Optional[str] = None
    receivers: Optional[List[Manager]] = None
    fill_nulls = make_fill_nulls()


class SillogData(BaseModel):
    description: Optional[Description] = None
    checklist: Optional[List[str]] = None
    outputs: Optional[List[Output]] = None
    fill_nulls = make_fill_nulls()

    @field_validator("checklist", mode="before")
    @classmethod
    def parse_checklist(cls, v):
        if not isinstance(v, list):
            if isinstance(v, str) and v:
                return [line.strip() for line in v.splitlines() if line.strip()]
            return v
        result = []
        for item in v:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                text = item.get("description") or item.get("title") or next(iter(item.values()), "")
                if text:
                    result.append(str(text))
        return result
