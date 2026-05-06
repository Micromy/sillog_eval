# -*- coding: utf-8 -*-
"""DB 컬럼 byte 길이 정의 (DDL과 일치).

VARCHAR2 컬럼은 `common.text.truncate(value, max_bytes)` 거쳐 INSERT.
"""


# ── eval_task_parsed* ──────────────────────────────

PARSED_COLUMN_BYTES = {
    "purpose": 2000,
    "task_execution_method": 4000,
    "tool": 200,
    "task_manager_role": 1000,
    "task_manager_role_type": 100,
    "task_manager_job_category": 100,
}

INPUT_COLUMN_BYTES = {
    "file_name": 500,
    "file_format": 50,
    "file_path": 2000,
    "task_link": 1000,
}

OUTPUT_COLUMN_BYTES = {
    "file_name": 500,
    "file_format": 50,
    "file_path": 2000,
}

MANAGER_COLUMN_BYTES = {
    "role": 200,
    "role_type": 100,
    "job_category": 100,
}


# ── eval_task_result* ──────────────────────────────

RESULT_COLUMN_BYTES = {
    "eval_summary": 2000,
    "model_name": 100,
    "comment_summary": 1000,
    "feedback": 4000,
    "review": 4000,
    "suggestion": 4000,
}
