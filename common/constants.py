# -*- coding: utf-8 -*-
"""정적 상수 (env 무관).

env 기반 설정은 `common/config.py`, DB 컬럼 길이는 `common/db/schema.py`.
"""


# ── 상태 코드 ──────────────────────────────────────

class PassFail:
    """평가 결과 상태."""
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"


class RuleType:
    """평가 규칙 종류 (eval_task_result_item.rule_type / 로컬 _meta items)."""
    QUANTITATIVE = "QUANTITATIVE"
    QUALITATIVE = "QUALITATIVE"


class ParentType:
    """eval_task_parsed_manager.parent_type."""
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"


class GradeCode:
    """eval_task_result.grade_code (감독관 검토 결과)."""
    APPROVED = "APPROVED"
    NOT_APPROVED = "NOT_APPRV"
    SUPERVISOR_FAILED = "SUP_FAIL"


class SupervisorStatus:
    """summary.supervisor.status (로컬 _meta.json)."""
    APPROVED = "approved"
    NOT_APPROVED = "not_approved"
    SUPERVISOR_FAILED = "supervisor_failed"
    UNKNOWN = "unknown"


class YN:
    """is_latest, pass_yn 등 Y/N 플래그."""
    YES = "Y"
    NO = "N"


# ── 매직 ID ────────────────────────────────────────

JIRA_KEY_ATTR_MASTER_ID = 17
"""sillog_tasks_attr.attr_master_id — Jira 키(예: PROJ-1234)와 task_id 매핑용."""


# ── 경로 / 파일명 ──────────────────────────────────

JIRA_CACHE_FILENAME = "jira_issues.pkl"
"""parse fetch_jira의 출력 캐시 파일명 (STORAGE_DIR 직하)."""

PARSED_SUBDIR = "parsed"
"""STORAGE_DIR 하위 — parse_description의 출력 디렉토리."""

FINAL_SUBDIR = "final"
"""평가 최종 결과 디렉토리 ({STORAGE_DIR}/{model_name}/final/)."""

ITEMS_SUBDIR = "items"
"""평가 항목별 결과 디렉토리 ({STORAGE_DIR}/{model_name}/final/{key}/items/)."""

ITERATION_SUBDIR = "iteration"
"""라운드별 스냅샷 디렉토리 ({STORAGE_DIR}/{model_name}/iteration/{key}/)."""

META_FILENAME = "_meta.json"
"""평가 메타 파일명."""

LOAD_ERROR_PREFIX = "_load_errors_"
"""save upload_parsed의 실패 로그 파일 prefix (`{prefix}{ts}.json`)."""

PARSE_ERROR_PREFIX = "_parse_errors_"
"""parse parse_description의 실패 로그 파일 prefix."""

BACKUP_SUFFIX = ".bak"
"""save migrate_meta의 백업 파일 suffix."""


# ── 청크 / 페이지 크기 ─────────────────────────────

JIRA_FETCH_LIMIT = 500
"""Jira JQL 페이지당 최대 이슈 수 (atlassian-python-api 기본값과 호환)."""

ORACLE_IN_CHUNK_SIZE = 500
"""Oracle IN 절 1000개 제한을 회피하기 위한 청크 크기."""


# ── Pass/Fail 점수 매핑 ───────────────────────────

SCORE_MAP = {
    PassFail.PASS: 1.0,
    PassFail.PARTIAL: 0.5,
    PassFail.FAIL: 0.0,
}
"""ChecklistResult.pass_fail → 0~1 점수. 균등 배점 계산용."""
