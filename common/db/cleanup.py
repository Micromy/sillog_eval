# -*- coding: utf-8 -*-
"""테스트 데이터 DB 정리 헬퍼.

특정 run_id prefix(예: `test_`)로 적재된 `eval_task_parsed*` 와 그것에 연결된
`eval_task_result*` 데이터를 자식 → 부모 순으로 삭제. 테스트 후 운영 데이터에
영향 없이 정리하기 위함.

[안전장치]
- 기본 dry-run. `execute=True` 명시해야 실삭제.
- 실삭제 전 영향 범위 출력.
- run_id prefix 매칭 (LIKE :prefix || '%'). prefix 짧으면 위험하므로 호출처에서 검증.
"""
from typing import Optional

from common import db
from common.constants import ORACLE_IN_CHUNK_SIZE


def cleanup_test_db(run_id_prefix: str, execute: bool = False) -> dict:
    """run_id LIKE prefix||'%' 인 parsed* + 연결된 result* 모두 삭제.

    Returns:
        {parsed_count, task_eval_count, deleted: {table: count}}
    """
    if not run_id_prefix or len(run_id_prefix) < 3:
        raise ValueError(f"run_id_prefix가 너무 짧음 ('{run_id_prefix}'). "
                         f"실수 방지를 위해 최소 3자 이상 필요.")

    # 1. 영향 범위 조회
    parsed_rows = db.select(
        """
        SELECT parsed_id, task_id, source_issue_key, status
        FROM eval_task_parsed
        WHERE run_id LIKE :prefix || '%'
        ORDER BY parsed_id
        """,
        prefix=run_id_prefix,
    )
    parsed_ids = [r["parsed_id"] for r in parsed_rows]
    task_ids = [r["task_id"] for r in parsed_rows if r["task_id"] is not None]

    task_eval_ids: list[int] = []
    if task_ids:
        # 같은 task_id로 적재된 모든 result row 식별
        for chunk_start in range(0, len(task_ids), ORACLE_IN_CHUNK_SIZE):
            chunk = task_ids[chunk_start: chunk_start + ORACLE_IN_CHUNK_SIZE]
            placeholders = ", ".join(f":t{i}" for i in range(len(chunk)))
            params = {f"t{i}": tid for i, tid in enumerate(chunk)}
            rows = db.select(
                f"""
                SELECT task_eval_id FROM eval_task_result
                WHERE task_id IN ({placeholders})
                """,
                **params,
            )
            task_eval_ids.extend(r["task_eval_id"] for r in rows)

    print(f"[cleanup_test_db] run_id_prefix='{run_id_prefix}'")
    print(f"  대상 parsed_id: {len(parsed_ids)}건")
    print(f"  대상 task_eval_id: {len(task_eval_ids)}건 (연결된 task_id {len(set(task_ids))}개)")

    if not parsed_ids and not task_eval_ids:
        print("  삭제 대상 없음. 종료.")
        return {"parsed_count": 0, "task_eval_count": 0, "deleted": {}}

    # 샘플 5개 표시
    if parsed_rows:
        print("\n  [샘플 (최대 5건)]")
        for r in parsed_rows[:5]:
            print(f"    parsed_id={r['parsed_id']:>6} task_id={r['task_id']} "
                  f"key={r['source_issue_key']} status={r['status']}")
        if len(parsed_rows) > 5:
            print(f"    ... 외 {len(parsed_rows) - 5}건")

    if not execute:
        print("\n  [DRY-RUN] 실제 삭제 없음. execute=True로 실삭제.")
        return {"parsed_count": len(parsed_ids), "task_eval_count": len(task_eval_ids), "deleted": {}}

    # 2. 삭제 (자식 → 부모 순, 한 트랜잭션)
    deleted: dict[str, int] = {}
    with db.cursor() as cur:
        # 2-1. eval_task_result 계열
        if task_eval_ids:
            for chunk_start in range(0, len(task_eval_ids), ORACLE_IN_CHUNK_SIZE):
                chunk = task_eval_ids[chunk_start: chunk_start + ORACLE_IN_CHUNK_SIZE]
                placeholders = ", ".join(f":id{i}" for i in range(len(chunk)))
                params = {f"id{i}": tid for i, tid in enumerate(chunk)}

                for tbl, col in [
                    ("eval_task_result_item_review", "task_eval_id"),
                    ("eval_task_result_review", "task_eval_result_id"),
                    ("eval_task_result_item", "task_eval_id"),
                    ("eval_task_result", "task_eval_id"),
                ]:
                    cur.execute(
                        f"DELETE FROM {tbl} WHERE {col} IN ({placeholders})",
                        **params,
                    )
                    deleted[tbl] = deleted.get(tbl, 0) + cur.rowcount

        # 2-2. eval_task_parsed 계열
        if parsed_ids:
            for chunk_start in range(0, len(parsed_ids), ORACLE_IN_CHUNK_SIZE):
                chunk = parsed_ids[chunk_start: chunk_start + ORACLE_IN_CHUNK_SIZE]
                placeholders = ", ".join(f":id{i}" for i in range(len(chunk)))
                params = {f"id{i}": pid for i, pid in enumerate(chunk)}

                for tbl in [
                    "eval_task_parsed_manager",
                    "eval_task_parsed_output",
                    "eval_task_parsed_input",
                    "eval_task_parsed_check",
                    "eval_task_parsed",
                ]:
                    cur.execute(
                        f"DELETE FROM {tbl} WHERE parsed_id IN ({placeholders})",
                        **params,
                    )
                    deleted[tbl] = deleted.get(tbl, 0) + cur.rowcount

    print("\n  [삭제 완료]")
    for tbl, cnt in deleted.items():
        print(f"    {tbl:>35}: {cnt:>6}건")

    return {
        "parsed_count": len(parsed_ids),
        "task_eval_count": len(task_eval_ids),
        "deleted": deleted,
    }
