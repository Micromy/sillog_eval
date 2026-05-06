# -*- coding: utf-8 -*-
"""
eval_task_parsed 계열 테이블 적재 모듈.
SillogData(Pydantic) → Oracle DB 적재.

[적재 순서]
1. eval_task_parsed       (루트)  → RETURNING parsed_id
2. eval_task_parsed_input (자식)  → RETURNING input_id  (manager FK용)
3. eval_task_parsed_output(자식)  → RETURNING output_id (manager FK용)
4. eval_task_parsed_check (자식)
5. eval_task_parsed_manager(자식) → parent_type='INPUT' | 'OUTPUT_RECEIVER'

[NULL 처리 정책]
- 필수 컬럼(run_id, source_issue_key 등): 누락 시 에러
- 선택 컬럼(file_name, file_path, role 등): 누락/빈문자열/None → NULL로 INSERT
"""

import json
from datetime import datetime
from typing import Any, Optional

from common import db
from common.convert import to_raw_dict
from common.text import truncate, clob_or_none, safe_dict, safe_list


# ── 단일 이슈 적재 ──────────────────────────────────────────────

def save_parsed(
    run_id: str,
    source_issue_key: str,
    sillog_data: Any,
    parser_version: str,
    task_id: Optional[int] = None,
) -> int:
    """SillogData 하나를 eval_task_parsed 계열 테이블에 적재.

    필수 인자(run_id, source_issue_key, sillog_data, parser_version)가 비어있으면 에러.
    선택 필드(file_name, role 등)가 누락된 경우는 NULL로 INSERT.

    Args:
        run_id: Airflow run_id (필수)
        source_issue_key: Jira 이슈 키 (예: PROJ-1234) (필수)
        sillog_data: SillogData Pydantic 인스턴스 또는 dict (필수)
        parser_version: 파서 버전 문자열 (필수)
        task_id: sillog_tasks.task_id (있으면)

    Returns:
        생성된 parsed_id

    Raises:
        ValueError: 필수 인자 누락 시
        TypeError: sillog_data 타입 불일치 시
        Exception: DB 오류 시 rollback 후 raise
    """
    # 필수 인자 검증
    if not run_id:
        raise ValueError("run_id가 비어있음")
    if not source_issue_key:
        raise ValueError("source_issue_key가 비어있음")
    if sillog_data is None:
        raise ValueError("sillog_data가 None")
    if not parser_version:
        raise ValueError("parser_version이 비어있음")

    data = to_raw_dict(sillog_data)
    raw_json = json.dumps(data, ensure_ascii=False, indent=2)
    desc = safe_dict(data.get("description"))

    # task_manager 평탄화 (없거나 dict 아니면 빈 dict)
    tm = safe_dict(desc.get("task_manager"))

    with db.cursor() as cur:
        # ── 1. 루트 INSERT ──
        parsed_id = _insert_parsed(
            cur,
            run_id=run_id,
            source_issue_key=source_issue_key,
            raw_json=raw_json,
            purpose=desc.get("purpose"),
            task_execution_method=desc.get("task_execution_method"),
            tool=desc.get("tool"),
            tm_role=tm.get("role"),
            tm_role_type=tm.get("role_type"),
            tm_job_category=tm.get("job_category"),
            parser_version=parser_version,
            task_id=task_id,
        )

        # ── 2. input_data INSERT ──
        for seq, inp in enumerate(safe_list(desc.get("input_data"))):
            inp = safe_dict(inp)
            input_id = _insert_input(cur, parsed_id, seq, inp)

            # input의 managers
            for mgr_seq, mgr in enumerate(safe_list(inp.get("managers"))):
                _insert_manager(
                    cur, parsed_id,
                    parent_type="INPUT",
                    parent_id=input_id,
                    seq=mgr_seq,
                    manager=safe_dict(mgr),
                )

        # ── 3. outputs INSERT ──
        for seq, out in enumerate(safe_list(data.get("outputs"))):
            out = safe_dict(out)
            output_id = _insert_output(cur, parsed_id, seq, out)

            # output의 receivers
            for rcv_seq, rcv in enumerate(safe_list(out.get("receivers"))):
                _insert_manager(
                    cur, parsed_id,
                    parent_type="OUTPUT",
                    parent_id=output_id,
                    seq=rcv_seq,
                    manager=safe_dict(rcv),
                )

        # ── 4. checklist INSERT ──
        for seq, item_text in enumerate(safe_list(data.get("checklist"))):
            _insert_check(cur, parsed_id, seq, item_text)

    return parsed_id


# ── 배치 적재 ────────────────────────────────────────────────

def save_parsed_batch(
    items: list[dict],
    run_id: str,
    parser_version: str,
) -> list[dict]:
    """여러 이슈 일괄 적재. 건별 트랜잭션 (한 건 실패해도 나머지 진행).

    Args:
        items: [{"source_issue_key": str, "sillog_data": ..., "task_id": int|None}, ...]
        run_id: Airflow run_id
        parser_version: 파서 버전

    Returns:
        [{"source_issue_key": str, "parsed_id": int|None, "error": str|None}, ...]
    """
    results = []

    for item in items:
        key = item["source_issue_key"]
        try:
            parsed_id = save_parsed(
                run_id=run_id,
                source_issue_key=key,
                sillog_data=item["sillog_data"],
                parser_version=parser_version,
                task_id=item.get("task_id"),
            )
            results.append({"source_issue_key": key, "parsed_id": parsed_id, "error": None})
            print(f"  [적재 OK] {key} → parsed_id={parsed_id}")
        except Exception as e:
            results.append({"source_issue_key": key, "parsed_id": None, "error": str(e)})
            print(f"  [적재 FAIL] {key}: {e}")

    success = sum(1 for r in results if r["error"] is None)
    print(f"[적재 완료] {success}/{len(results)} 성공")
    return results


# ── 조회 헬퍼 ────────────────────────────────────────────────

def get_latest_parsed(source_issue_key: str) -> Optional[dict]:
    """특정 이슈의 최신 파싱 결과 조회.

    Returns:
        eval_task_parsed 행 dict 또는 None
    """
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
        SELECT parsed_id, source_issue_key, purpose, tool, parsed_at
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
    """이슈 키 목록에 대해 최신 파싱의 raw_json 해시를 반환.

    diff_and_filter에서 변경 감지에 사용.

    Returns:
        {source_issue_key: raw_json_hash}
    """
    if not issue_keys:
        return {}

    # Oracle IN절 최대 1000개 제한 → 청크 분할
    result = {}
    for chunk_start in range(0, len(issue_keys), 500):
        chunk = issue_keys[chunk_start : chunk_start + 500]
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
            )
            WHERE rn = 1
            """,
            **params,
        )
        for row in rows:
            result[row["source_issue_key"]] = row["raw_hash"]

    return result


# ── private: 테이블별 INSERT ─────────────────────────────────

def _insert_parsed(
    cur,
    run_id: str,
    source_issue_key: str,
    raw_json: str,
    purpose: Optional[str],
    task_execution_method: Optional[str],
    tool: Optional[str],
    tm_role: Optional[str],
    tm_role_type: Optional[str],
    tm_job_category: Optional[str],
    parser_version: str,
    task_id: Optional[int] = None,
) -> int:
    """eval_task_parsed INSERT → parsed_id 반환."""
    import oracledb

    parsed_id_var = cur.var(oracledb.NUMBER)
    cur.execute(
        """
        INSERT INTO eval_task_parsed (
            run_id,
            task_id,
            raw_json,
            purpose, 
            task_execution_method, 
            tool,
            task_manager_role, 
            task_manager_role_type, 
            task_manager_job_category,
            parsed_at, 
            parser_version
        ) VALUES (
            :run_id, 
            (SELECT task_id 
             FROM sillog_tasks_attr 
             WHERE attr_master_id=17 and attr_value=:issue_key), 
            :raw_json,
            :purpose, 
            :exec_method, 
            :tool,
            :tm_role, 
            :tm_role_type, 
            :tm_job_cat,
            :parsed_at, 
            :parser_ver
        )
        RETURNING parsed_id INTO :out_id
        """,
        run_id=run_id,
        issue_key=source_issue_key,
        raw_json=raw_json,
        purpose=truncate(purpose, 2000),
        exec_method=truncate(task_execution_method, 4000),
        tool=truncate(tool, 200),
        tm_role=truncate(tm_role, 1000),
        tm_role_type=truncate(tm_role_type, 100),
        tm_job_cat=truncate(tm_job_category, 100),
        parsed_at=datetime.now(),
        parser_ver=parser_version,
        out_id=parsed_id_var,
    )
    return int(parsed_id_var.getvalue()[0])


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
        fname=truncate(inp.get("file_name"), 500),
        fformat=truncate(inp.get("file_format"), 50),
        fpath=truncate(inp.get("file_path"), 2000),
        descr=clob_or_none(inp.get("description")),
        tlink=truncate(inp.get("task_link"), 1000),
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
        fname=truncate(out.get("file_name"), 500),
        fformat=truncate(out.get("file_format"), 50),
        fpath=truncate(out.get("file_path"), 2000),
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
        role=truncate(manager.get("role"), 200),
        rtype=truncate(manager.get("role_type"), 100),
        jcat=truncate(manager.get("job_category"), 100),
    )


# ── 일괄 업로드 (디렉토리 → DB) ────────────────────────────────

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
    """parsed/*.json 일괄 적재.

    UK 위반은 skip, 그 외 실패는 _load_errors_<ts>.json에 누적 저장.

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
    errors_log: list[dict] = []

    for i, filepath in enumerate(files, 1):
        key = filepath.stem
        prefix = f"  [{i}/{len(files)}] {key}"

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"{prefix}: JSON 파싱 실패 - {e}")
            errors_log.append({"key": key, "error": f"JSON 파싱 실패: {e}"})
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
                errors_log.append({"key": key, "error": error_msg})
                failed += 1

    print(f"\n{'='*50}")
    print(f"[결과] 전체={len(files)} | 성공={success} | 스킵={skipped} | 실패={failed}")

    if errors_log:
        print(f"\n[실패 목록]")
        for err in errors_log:
            print(f"  - {err['key']}: {err['error']}")

        error_log_path = parsed_dir / f"_load_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(error_log_path, "w", encoding="utf-8") as f:
            json.dump(errors_log, f, ensure_ascii=False, indent=2)
        print(f"\n  에러 로그 저장: {error_log_path}")

    return success, skipped, failed
