# -*- coding: utf-8 -*-
"""
eval_task_parsed 계열 테이블 적재 모듈.

[적재 패턴]
1. `insert_parsed_placeholder(cur, run_id, source_issue_key, parser_version)`
   → status='PENDING' row만 INSERT (raw_json/자식 NULL). parsed_id 반환.
2. LLM 호출 등 외부 작업 수행 (DB connection 안 잡고)
3. 성공 시 `populate_parsed(cur, parsed_id, sillog_data)`
   → eval_task_parsed UPDATE (raw_json + 메타) + 자식 4개 INSERT + status='DONE'
   (한 트랜잭션)
4. 실패 시 `mark_parsed_failed(parsed_id, reason)`
   → status='FAILED' + failed_reason 컬럼 기록

[자식 테이블 적재 순서]
- eval_task_parsed_input  (RETURNING input_id  → manager FK)
- eval_task_parsed_output (RETURNING output_id → manager FK)
- eval_task_parsed_check
- eval_task_parsed_manager (parent_type='INPUT' | 'OUTPUT')

[NULL 처리]
- 필수 인자(run_id, source_issue_key, parser_version): 누락 시 ValueError
- 선택 필드(file_name, role 등): 누락/빈문자열/None → NULL INSERT

[재개]
`get_done_keys(run_id)`: status='DONE'인 source_issue_key 집합. parse_description 시작 시
이걸로 skip 대상을 계산.
"""

import json
from datetime import datetime
from typing import Any, Optional, Set

from common import db
from common.constants import (
    JIRA_KEY_ATTR_MASTER_ID,
    ORACLE_IN_CHUNK_SIZE,
    ParentType,
    Status,
)
from common.convert import to_raw_dict
from common.db.schema import (
    INPUT_COLUMN_BYTES,
    MANAGER_COLUMN_BYTES,
    OUTPUT_COLUMN_BYTES,
    PARSED_COLUMN_BYTES,
)
from common.text import truncate, clob_or_none, safe_dict, safe_list


# ── placeholder / populate / mark_failed ────────────────────────

def insert_parsed_placeholder(
    cur,
    run_id: str,
    source_issue_key: str,
    parser_version: str,
) -> int:
    """eval_task_parsed에 placeholder 1행 INSERT (status='PENDING').

    raw_json/메타 컬럼은 NULL. 자식 테이블은 아직 INSERT하지 않음.

    Returns:
        생성된 parsed_id

    Raises:
        ValueError: 필수 인자 누락
    """
    if not run_id:
        raise ValueError("run_id가 비어있음")
    if not source_issue_key:
        raise ValueError("source_issue_key가 비어있음")
    if not parser_version:
        raise ValueError("parser_version이 비어있음")

    import oracledb
    parsed_id_var = cur.var(oracledb.NUMBER)
    cur.execute(
        """
        INSERT INTO eval_task_parsed (
            run_id,
            task_id,
            source_issue_key,
            parsed_at,
            parser_version,
            status
        ) VALUES (
            :run_id,
            (SELECT task_id
             FROM sillog_tasks_attr
             WHERE attr_master_id=:master_id AND attr_value=:issue_key),
            :issue_key,
            :parsed_at,
            :parser_ver,
            :status
        )
        RETURNING parsed_id INTO :out_id
        """,
        run_id=run_id,
        master_id=JIRA_KEY_ATTR_MASTER_ID,
        issue_key=source_issue_key,
        parsed_at=datetime.now(),
        parser_ver=parser_version,
        status=Status.PENDING,
        out_id=parsed_id_var,
    )
    return int(parsed_id_var.getvalue()[0])


def populate_parsed(cur, parsed_id: int, sillog_data: Any) -> None:
    """placeholder row를 채워 status='DONE'으로 마무리.

    eval_task_parsed UPDATE (raw_json + 메타) + 자식 4개 INSERT.
    호출자가 `with db.cursor() as cur:` 안에서 호출 (한 트랜잭션 commit).
    """
    if sillog_data is None:
        raise ValueError("sillog_data가 None")

    data = to_raw_dict(sillog_data)
    raw_json = json.dumps(data, ensure_ascii=False, indent=2)
    desc = safe_dict(data.get("description"))
    tm = safe_dict(desc.get("task_manager"))

    # 1. 본문 + 메타 UPDATE (status DONE)
    cur.execute(
        """
        UPDATE eval_task_parsed
        SET raw_json = :raw_json,
            purpose = :purpose,
            task_execution_method = :exec_method,
            tool = :tool,
            task_manager_role = :tm_role,
            task_manager_role_type = :tm_role_type,
            task_manager_job_category = :tm_job_cat,
            status = :status,
            failed_reason = NULL
        WHERE parsed_id = :pid
        """,
        pid=parsed_id,
        raw_json=raw_json,
        purpose=truncate(desc.get("purpose"), PARSED_COLUMN_BYTES["purpose"]),
        exec_method=truncate(desc.get("task_execution_method"), PARSED_COLUMN_BYTES["task_execution_method"]),
        tool=truncate(desc.get("tool"), PARSED_COLUMN_BYTES["tool"]),
        tm_role=truncate(tm.get("role"), PARSED_COLUMN_BYTES["task_manager_role"]),
        tm_role_type=truncate(tm.get("role_type"), PARSED_COLUMN_BYTES["task_manager_role_type"]),
        tm_job_cat=truncate(tm.get("job_category"), PARSED_COLUMN_BYTES["task_manager_job_category"]),
        status=Status.DONE,
    )

    # 2. input INSERT + 그 input의 managers
    for seq, inp in enumerate(safe_list(desc.get("input_data"))):
        inp = safe_dict(inp)
        input_id = _insert_input(cur, parsed_id, seq, inp)
        for mgr_seq, mgr in enumerate(safe_list(inp.get("managers"))):
            _insert_manager(
                cur, parsed_id,
                parent_type=ParentType.INPUT,
                parent_id=input_id,
                seq=mgr_seq,
                manager=safe_dict(mgr),
            )

    # 3. output INSERT + 그 output의 receivers
    for seq, out in enumerate(safe_list(data.get("outputs"))):
        out = safe_dict(out)
        output_id = _insert_output(cur, parsed_id, seq, out)
        for rcv_seq, rcv in enumerate(safe_list(out.get("receivers"))):
            _insert_manager(
                cur, parsed_id,
                parent_type=ParentType.OUTPUT,
                parent_id=output_id,
                seq=rcv_seq,
                manager=safe_dict(rcv),
            )

    # 4. checklist INSERT
    for seq, item_text in enumerate(safe_list(data.get("checklist"))):
        _insert_check(cur, parsed_id, seq, item_text)


def mark_parsed_failed(parsed_id: int, reason: str) -> None:
    """status='FAILED' + failed_reason 기록. 별도 트랜잭션."""
    db.execute(
        """
        UPDATE eval_task_parsed
        SET status = :status,
            failed_reason = :reason
        WHERE parsed_id = :pid
        """,
        pid=parsed_id,
        status=Status.FAILED,
        reason=truncate(reason, PARSED_COLUMN_BYTES["failed_reason"]),
    )


# ── 재개 (resume) ───────────────────────────────────────────────

def get_done_keys(run_id: str) -> Set[str]:
    """status='DONE'인 source_issue_key 집합 (재개 시 skip 대상)."""
    rows = db.select(
        """
        SELECT source_issue_key
        FROM eval_task_parsed
        WHERE run_id = :rid AND status = :status
        """,
        rid=run_id,
        status=Status.DONE,
    )
    return {r["source_issue_key"] for r in rows}


# ── 후행 호환 / backfill 용 ──────────────────────────────────────

def save_parsed(
    run_id: str,
    source_issue_key: str,
    sillog_data: Any,
    parser_version: str,
    task_id: Optional[int] = None,  # 사용 안 함 (서브쿼리로 매핑) — 시그니처 호환용
) -> int:
    """[backfill용] placeholder + populate를 한 트랜잭션에 묶어 호출.

    `save upload_parsed` task에서 로컬 parsed JSON → DB 적재 시 사용.
    평소 파이프라인(parse_description)은 placeholder/populate를 분리 호출.
    """
    if sillog_data is None:
        raise ValueError("sillog_data가 None")

    with db.cursor() as cur:
        parsed_id = insert_parsed_placeholder(cur, run_id, source_issue_key, parser_version)
        populate_parsed(cur, parsed_id, sillog_data)
        return parsed_id


# ── 조회 헬퍼 ────────────────────────────────────────────────

def get_latest_parsed(source_issue_key: str) -> Optional[dict]:
    """특정 이슈의 최신 파싱 결과 조회."""
    return db.fetch(
        """
        SELECT *
        FROM eval_task_parsed
        WHERE source_issue_key = :key
        ORDER BY parsed_at DESC
        FETCH FIRST 1 ROW ONLY
        """,
        key=source_issue_key,
    )


def get_parsed_by_run(run_id: str) -> list[dict]:
    """특정 run의 모든 파싱 결과 조회."""
    return db.select(
        """
        SELECT parsed_id, source_issue_key, purpose, tool, parsed_at, status
        FROM eval_task_parsed
        WHERE run_id = :rid
        ORDER BY parsed_id
        """,
        rid=run_id,
    )


def get_parsed_full(parsed_id: int) -> Optional[dict]:
    """parsed_id로 루트 + raw_json 조회. LLM 평가 입력용."""
    return db.fetch(
        "SELECT * FROM eval_task_parsed WHERE parsed_id = :pid",
        pid=parsed_id,
    )


def get_existing_hashes(issue_keys: list[str]) -> dict[str, str]:
    """이슈 키 목록 → 최신 파싱의 raw_json 해시. 변경 감지용."""
    if not issue_keys:
        return {}

    result = {}
    for chunk_start in range(0, len(issue_keys), ORACLE_IN_CHUNK_SIZE):
        chunk = issue_keys[chunk_start: chunk_start + ORACLE_IN_CHUNK_SIZE]
        placeholders = ", ".join(f":k{i}" for i in range(len(chunk)))
        params = {f"k{i}": key for i, key in enumerate(chunk)}

        rows = db.select(
            f"""
            SELECT source_issue_key,
                   DBMS_CRYPTO.HASH(UTL_RAW.CAST_TO_RAW(raw_json), 4) AS raw_hash
            FROM (
                SELECT source_issue_key, raw_json,
                       ROW_NUMBER() OVER (
                           PARTITION BY source_issue_key
                           ORDER BY parsed_at DESC
                       ) AS rn
                FROM eval_task_parsed
                WHERE source_issue_key IN ({placeholders})
                  AND status = '{Status.DONE}'
            )
            WHERE rn = 1
            """,
            **params,
        )
        for row in rows:
            result[row["source_issue_key"]] = row["raw_hash"]

    return result


# ── private: 자식 테이블 INSERT ──────────────────────────────────

def _insert_input(cur, parsed_id: int, seq: int, inp: dict) -> int:
    """eval_task_parsed_input INSERT → input_id 반환."""
    import oracledb

    input_id_var = cur.var(oracledb.NUMBER)
    cur.execute(
        """
        INSERT INTO eval_task_parsed_input (
            parsed_id,
            seq,
            file_name,
            file_format,
            file_path,
            description,
            task_link
        ) VALUES (
            :pid,
            :seq,
            :fname,
            :fformat,
            :fpath,
            :descr,
            :tlink
        )
        RETURNING input_id INTO :out_id
        """,
        pid=parsed_id,
        seq=seq,
        fname=truncate(inp.get("file_name"), INPUT_COLUMN_BYTES["file_name"]),
        fformat=truncate(inp.get("file_format"), INPUT_COLUMN_BYTES["file_format"]),
        fpath=truncate(inp.get("file_path"), INPUT_COLUMN_BYTES["file_path"]),
        descr=clob_or_none(inp.get("description")),
        tlink=truncate(inp.get("task_link"), INPUT_COLUMN_BYTES["task_link"]),
        out_id=input_id_var,
    )
    return int(input_id_var.getvalue()[0])


def _insert_output(cur, parsed_id: int, seq: int, out: dict) -> int:
    """eval_task_parsed_output INSERT → output_id 반환."""
    import oracledb

    output_id_var = cur.var(oracledb.NUMBER)
    cur.execute(
        """
        INSERT INTO eval_task_parsed_output (
            parsed_id,
            seq,
            file_name,
            file_format,
            file_path
        ) VALUES (
            :pid,
            :seq,
            :fname,
            :fformat,
            :fpath
        )
        RETURNING output_id INTO :out_id
        """,
        pid=parsed_id,
        seq=seq,
        fname=truncate(out.get("file_name"), OUTPUT_COLUMN_BYTES["file_name"]),
        fformat=truncate(out.get("file_format"), OUTPUT_COLUMN_BYTES["file_format"]),
        fpath=truncate(out.get("file_path"), OUTPUT_COLUMN_BYTES["file_path"]),
        out_id=output_id_var,
    )
    return int(output_id_var.getvalue()[0])


def _insert_check(cur, parsed_id: int, seq: int, item_text) -> None:
    """eval_task_parsed_check INSERT."""
    cur.execute(
        """
        INSERT INTO eval_task_parsed_check (
            parsed_id,
            seq,
            item_text
        ) VALUES (
            :pid,
            :seq,
            :item
        )
        """,
        pid=parsed_id,
        seq=seq,
        item=clob_or_none(item_text),
    )


def _insert_manager(
    cur,
    parsed_id: int,
    parent_type: str,
    parent_id: int,
    seq: int,
    manager: dict,
) -> None:
    """eval_task_parsed_manager INSERT."""
    cur.execute(
        """
        INSERT INTO eval_task_parsed_manager (
            parsed_id,
            parent_type,
            parent_id,
            seq,
            role,
            role_type,
            job_category
        ) VALUES (
            :pid,
            :ptype,
            :parent_id,
            :seq,
            :role,
            :rtype,
            :jcat
        )
        """,
        pid=parsed_id,
        ptype=parent_type,
        parent_id=parent_id,
        seq=seq,
        role=truncate(manager.get("role"), MANAGER_COLUMN_BYTES["role"]),
        rtype=truncate(manager.get("role_type"), MANAGER_COLUMN_BYTES["role_type"]),
        jcat=truncate(manager.get("job_category"), MANAGER_COLUMN_BYTES["job_category"]),
    )


# ── 일괄 업로드 (backfill: 디렉토리 → DB) ────────────────────────

def _discover_files(parsed_dir):
    """디렉터리에서 {key}.json 파일 목록 수집 (에러 로그 제외)."""
    import sys

    if not parsed_dir.exists():
        print(f"[ERROR] 디렉터리 없음: {parsed_dir}")
        sys.exit(1)

    all_files = sorted(parsed_dir.glob("*.json"))
    files = [f for f in all_files if not f.name.startswith("_")]
    if not files:
        print(f"[WARN] JSON 파일 없음: {parsed_dir}")
        sys.exit(0)
    return files, len(all_files) - len(files)


def _validate_sillog_structure(data: dict) -> list[str]:
    """최소 구조 검증. 에러 메시지 리스트 (빈 리스트 = 정상)."""
    errors = []
    if "description" not in data:
        errors.append("description 필드 없음")
    else:
        desc = data["description"]
        if "purpose" not in desc:
            errors.append("description.purpose 필드 없음")
        if "input_data" not in desc:
            errors.append("description.input_data 필드 없음")
    if "checklist" not in data:
        errors.append("checklist 필드 없음")
    if "outputs" not in data:
        errors.append("outputs 필드 없음")
    return errors


def upload(
    parsed_dir,
    run_id: str,
    parser_version: str,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """parsed/*.json 일괄 적재 (backfill용).

    UK 위반은 skip, 그 외 실패는 콘솔 출력만. 평소 파이프라인은 parse_description이
    DB 적재까지 같이 하므로 이 함수는 backfill 시나리오에서만 사용.

    Returns: (success, skipped, failed)
    """
    files, excluded = _discover_files(parsed_dir)

    print(f"[시작] {len(files)}개 파일 발견 | run_id={run_id} | parser_version={parser_version}")
    if excluded:
        print(f"  (에러 로그 등 {excluded}개 제외)")
    if dry_run:
        print("[DRY-RUN] DB 적재 없이 검증만 수행합니다.\n")

    success = 0
    skipped = 0
    failed = 0

    for i, filepath in enumerate(files, 1):
        key = filepath.stem
        prefix = f"  [{i}/{len(files)}] {key}"

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"{prefix}: JSON 파싱 실패 - {e}")
            failed += 1
            continue

        validation_errors = _validate_sillog_structure(data)
        warning_msg = f" [구조 부족: {'; '.join(validation_errors)}]" if validation_errors else ""

        if dry_run:
            desc = data.get("description", {}) or {}
            input_count = len(desc.get("input_data") or [])
            output_count = len(data.get("outputs") or [])
            check_count = len(data.get("checklist") or [])
            print(f"{prefix}: OK (input={input_count}, output={output_count}, check={check_count}){warning_msg}")
            success += 1
            continue

        try:
            parsed_id = save_parsed(
                run_id=run_id,
                source_issue_key=key,
                sillog_data=data,
                parser_version=parser_version,
            )
            print(f"{prefix}: 적재 완료 → parsed_id={parsed_id}{warning_msg}")
            success += 1
        except Exception as e:
            error_msg = str(e)
            if "uk_parsed" in error_msg.lower() or "unique constraint" in error_msg.lower():
                print(f"{prefix}: 이미 적재됨 (skip)")
                skipped += 1
            else:
                print(f"{prefix}: 적재 실패 - {error_msg}")
                failed += 1

    print(f"\n{'='*50}")
    print(f"[결과] 전체={len(files)} | 성공={success} | 스킵={skipped} | 실패={failed}")
    return success, skipped, failed
