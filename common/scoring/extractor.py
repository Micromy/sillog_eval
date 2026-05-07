# -*- coding: utf-8 -*-
"""
SillogData Extractor - Extract relevant information from SillogData structure
"""
from typing import Dict, Any

from common.convert import to_raw_dict


class SillogDataExtractor:
    """
    SillogData Pydantic BaseModel 또는 dict에서 필요한 정보 추출
    """

    @staticmethod
    def extract(sillog_data) -> Dict[str, Any]:
        data = to_raw_dict(sillog_data)

        description = data.get("description", {})
        outputs = data.get("outputs", [])
        checklist_items = data.get("checklist", [])

        purpose = description.get("purpose", "") if isinstance(description, dict) else ""

        input_data_info = []
        input_data_list = description.get("input_data", []) if isinstance(description, dict) else []
        for inp in input_data_list:
            if isinstance(inp, dict):
                managers_info = ""
                managers = inp.get("managers", [])
                manager_list = []
                for m in managers:
                    if isinstance(m, dict):
                        manager_list.append(f"{m.get('job_category', '')}->{m.get('role_type', '')}->{m.get('role', '')}")
                if manager_list:
                    managers_info = " / ".join(manager_list)

                input_text_parts = []
                if inp.get("file_name"):
                    input_text_parts.append(f"파일명: {inp['file_name']}")
                if inp.get("file_format"):
                    input_text_parts.append(f"포맷: {inp['file_format']}")
                if inp.get("file_path"):
                    input_text_parts.append(f"위치: {inp['file_path']}")
                if inp.get("description"):
                    input_text_parts.append(f"설명: {inp['description']}")
                if inp.get("task_link"):
                    input_text_parts.append(f"Task link: {inp['task_link']}")
                if managers_info:
                    input_text_parts.append(f"담당자: {managers_info}")

                input_data_info.append(" | ".join(input_text_parts))

        input_data_combined = " | ".join(input_data_info)

        task_owner_info = ""
        if isinstance(description, dict):
            task_manager = description.get("task_manager", {})
            if isinstance(task_manager, dict):
                task_owner_info = f"{task_manager.get('job_category', '')}->{task_manager.get('role_type', '')}->{task_manager.get('role', '')}"

        task_method = description.get("task_execution_method", "") if isinstance(description, dict) else ""
        tool_info = description.get("tool", "") if isinstance(description, dict) else ""

        task_parts = []
        if task_method:
            task_parts.append(f"수행방법: {task_method}")
        if tool_info:
            task_parts.append(f"Tool: {tool_info}")
        if task_owner_info:
            task_parts.append(f"Owner: {task_owner_info}")
        task_combined = " | ".join(task_parts)

        output_info = []
        for out in outputs:
            if isinstance(out, dict):
                receivers_info = ""
                receivers = out.get("receivers", [])
                receiver_list = []
                for r in receivers:
                    if isinstance(r, dict):
                        receiver_list.append(f"{r.get('job_category', '')}->{r.get('role_type', '')}->{r.get('role', '')}")
                if receiver_list:
                    receivers_info = " / ".join(receiver_list)

                output_parts = []
                if out.get("file_name"):
                    output_parts.append(f"파일명: {out['file_name']}")
                if out.get("file_format"):
                    output_parts.append(f"포맷: {out['file_format']}")
                if out.get("file_path"):
                    output_parts.append(f"위치: {out['file_path']}")
                if receivers_info:
                    output_parts.append(f"Receiver: {receivers_info}")

                output_info.append(" | ".join(output_parts))

        output_combined = " | ".join(output_info)
        checklist_combined = " | ".join([str(c) for c in checklist_items]) if checklist_items else ""

        return {
            "purpose": purpose,
            "input_data": input_data_combined,
            "task": task_combined,
            "output": output_combined,
            "checklist": checklist_combined
        }
