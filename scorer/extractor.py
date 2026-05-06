# -*- coding: utf-8 -*-
"""
SillogData Extractor - Extract relevant information from SillogData structure
"""
from typing import Dict, Any


class SillogDataExtractor:
    """
    SillogData Pydantic BaseModel 또는 dict에서 필요한 정보 추출
    """

    @staticmethod
    def extract(sillog_data) -> Dict[str, Any]:
        # dict 형식
        if isinstance(sillog_data, dict):
            description = sillog_data.get("description", {})
            outputs = sillog_data.get("outputs", [])
            checklist = sillog_data.get("checklist", [])

            goal = description.get("purpose", "") if isinstance(description, dict) else ""

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
            completion_combined = " | ".join([str(c) for c in checklist]) if checklist else ""

            return {
                "goal": goal,
                "input_data": input_data_combined,
                "task": task_combined,
                "output": output_combined,
                "completion": completion_combined
            }

        # Pydantic BaseModel 형식
        description = sillog_data.description
        outputs = sillog_data.outputs
        checklist = sillog_data.checklist

        goal = description.purpose if description.purpose else ""

        input_data_info = []
        for inp in description.input_data:
            managers_info = ""
            if inp.managers:
                manager_list = [f"{m.job_category}->{m.role_type}->{m.role}" for m in inp.managers]
                managers_info = " / ".join(manager_list)

            input_text_parts = []
            if inp.file_name:
                input_text_parts.append(f"파일명: {inp.file_name}")
            if inp.file_format:
                input_text_parts.append(f"포맷: {inp.file_format}")
            if inp.file_path:
                input_text_parts.append(f"위치: {inp.file_path}")
            if inp.description:
                input_text_parts.append(f"설명: {inp.description}")
            if inp.task_link:
                input_text_parts.append(f"Task link: {inp.task_link}")
            if managers_info:
                input_text_parts.append(f"담당자: {managers_info}")

            input_data_info.append(" | ".join(input_text_parts))

        input_data_combined = " | ".join(input_data_info)

        task_owner_info = ""
        if description.task_manager:
            task_owner_info = f"{description.task_manager.job_category}->{description.task_manager.role_type}->{description.task_manager.role}"

        task_method = description.task_execution_method if description.task_execution_method else ""
        tool_info = description.tool if description.tool else ""

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
            receivers_info = ""
            if out.receivers:
                receiver_list = [f"{r.job_category}->{r.role_type}->{r.role}" for r in out.receivers]
                receivers_info = " / ".join(receiver_list)

            output_parts = []
            if out.file_name:
                output_parts.append(f"파일명: {out.file_name}")
            if out.file_format:
                output_parts.append(f"포맷: {out.file_format}")
            if out.file_path:
                output_parts.append(f"위치: {out.file_path}")
            if receivers_info:
                output_parts.append(f"Receiver: {receivers_info}")

            output_info.append(" | ".join(output_parts))

        output_combined = " | ".join(output_info)
        completion_combined = " | ".join(checklist) if checklist else ""

        return {
            "goal": goal,
            "input_data": input_data_combined,
            "task": task_combined,
            "output": output_combined,
            "completion": completion_combined
        }
