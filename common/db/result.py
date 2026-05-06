"""평가 결과(IssueScore + items) → eval_task_result* 테이블 마이그레이션.

[입력]
{storage_dir}/{model_name}/final/{key}/
    _meta.json
    items/{criterion_name}.json

[매핑]
- 로컬 criterion_name == DB eval_task_rule_item.item_name
- avail='Y' 항목만 매핑 대상 (rule_set 무관, 합집합)
- eval_task_result.eval_rule_set_id는 매핑된 항목들의 max(eval_rule_set_id)

[중복 처리]
같은 (task_id, eval_rule_set_id, eval_seq) 발견 시 자식 → 부모 순으로 삭제 후 재적재.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from common import db
from common.text import truncate


# ── rule_item 매핑 로드 ─────────────────────────────

def load_active_rule_items() -> Tuple[Dict[str, int], int]:
    """활성 rule_item 매핑 로드.

    Returns:
        (mapping: {item_name: eval_rule_item_id}, latest_rule_set_id: int)
    """
    rows = db.select(
        """
        SELECT eval_rule_item_id, eval_rule_set_id, item_name
        FROM eval_task_rule_item
        WHERE avail = 'Y'
        """,
    )
    if not rows:
        raise RuntimeError("활성 rule_item이 없음")

    mapping = {row["item_name"]: row["eval_rule_item_id"] for row in rows}
    latest_rule_set_id = max(row["eval_rule_set_id"] for row in rows)

    return mapping, latest_rule_set_id


# ── task_id 조회 ──────────────────────────────────

def lookup_task_id(cur, jira_key: str) -> Optional[int]:
    """Jira key → sillog_tasks.task_id 조회"""
    cur.execute(
        """
        SELECT task_id
        FROM sillog_tasks_attr
        WHERE attr_master_id = 17 AND attr_value = :key
        """,
        key=jira_key,
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


# ── 기존 데이터 삭제 ───────────────────────────────

def delete_existing_result(cur, task_id: int, eval_rule_set_id: int, eval_seq: int) -> bool:
    """같은 (task_id, eval_rule_set_id, eval_seq) 결과를 자식 → 부모 순으로 삭제"""
    cur.execute(
        """
        SELECT task_eval_id
        FROM eval_task_result
        WHERE task_id = :tid
          AND eval_rule_set_id = :rsid
          AND eval_seq = :seq
        """,
        tid=task_id, rsid=eval_rule_set_id, seq=eval_seq,
    )
    row = cur.fetchone()
    if not row:
        return False

    task_eval_id = int(row[0])

    cur.execute("DELETE FROM eval_task_result_item_review WHERE task_eval_id = :tid", tid=task_eval_id)
    cur.execute("DELETE FROM eval_task_result_review WHERE task_eval_result_id = :tid", tid=task_eval_id)
    cur.execute("DELETE FROM eval_task_result_item WHERE task_eval_id = :tid", tid=task_eval_id)
    cur.execute("DELETE FROM eval_task_result WHERE task_eval_id = :tid", tid=task_eval_id)
    return True


# ── INSERT 함수들 ──────────────────────────────────

def insert_result(
    cur, task_id: int, eval_rule_set_id: int, meta: dict,
    migration_time: datetime, model_name: str,
) -> int:
    """eval_task_result INSERT → task_eval_id 반환"""
    import oracledb

    summary = meta.get("summary") or {}
    supervisor = summary.get("supervisor") or {}

    task_eval_id_var = cur.var(oracledb.NUMBER)
    cur.execute(
        """
        INSERT INTO eval_task_result (
            task_id, eval_rule_set_id, eval_seq,
            total_score, grade_code, eval_count,
            eval_summary, is_latest,
            evaluated_at, evaluated_by,
            model_name,
            created_at, created_by, updated_at, updated_by
        ) VALUES (
            :task_id, :rsid, :seq,
            :total_score, :grade_code, :eval_count,
            :eval_summary, 'Y',
            :evaluated_at, :evaluated_by,
            :model_name,
            :created_at, :created_by, :updated_at, :updated_by
        )
        RETURNING task_eval_id INTO :out_id
        """,
        task_id=task_id,
        rsid=eval_rule_set_id,
        seq=meta.get("eval_seq", 1),
        total_score=summary.get("final_score"),
        grade_code=_grade_from_status(supervisor.get("status")),
        eval_count=summary.get("rounds_used"),
        eval_summary=truncate(meta.get("total_summary"), 2000),
        evaluated_at=migration_time,
        evaluated_by="migration",
        model_name=truncate(model_name, 100),
        created_at=migration_time,
        created_by="migration",
        updated_at=migration_time,
        updated_by="migration",
        out_id=task_eval_id_var,
    )
    return int(task_eval_id_var.getvalue()[0])


def insert_result_items(
    cur, task_eval_id: int, items_dir: Path,
    rule_item_map: Dict[str, int],
    migration_time: datetime,
) -> Tuple[int, List[str]]:
    """items/*.json INSERT → (성공건수, 매핑실패 리스트)"""
    if not items_dir.exists():
        return 0, []

    success = 0
    unmapped = []

    for item_file in sorted(items_dir.glob("*.json")):
        try:
            with open(item_file, encoding="utf-8") as f:
                item = json.load(f)
        except Exception as e:
            print(f"    [warn] {item_file.name} 로드 실패: {e}")
            continue

        criterion_name = item.get("criterion_name")
        eval_rule_item_id = rule_item_map.get(criterion_name)
        if eval_rule_item_id is None:
            unmapped.append(criterion_name)
            continue

        pass_fail = item.get("pass_fail", "FAIL")
        raw_score = _score_from_pass_fail(pass_fail)

        cur.execute(
            """
            INSERT INTO eval_task_result_item (
                task_eval_id, eval_rule_item_id,
                raw_score, weighted_score, pass_yn, comment_summary,
                created_at, created_by, updated_at, updated_by
            ) VALUES (
                :tid, :rid,
                :raw_sc, :weighted, :pass_yn, :cmt,
                :created_at, :created_by, :updated_at, :updated_by
            )
            """,
            tid=task_eval_id,
            rid=eval_rule_item_id,
            raw_sc=raw_score,
            weighted=raw_score,
            pass_yn=_pass_yn(pass_fail),
            cmt=truncate(item.get("reasoning"), 1000),
            created_at=migration_time,
            created_by="migration",
            updated_at=migration_time,
            updated_by="migration",
        )
        success += 1

    return success, unmapped


def insert_result_reviews(
    cur, task_eval_id: int, review_history: List[dict],
    migration_time: datetime,
) -> int:
    """review_history → eval_task_result_review INSERT"""
    count = 0
    for entry in review_history:
        cur.execute(
            """
            INSERT INTO eval_task_result_review (
                task_eval_result_id, feedback, eval_seq, time_elapsed,
                created_at, created_by
            ) VALUES (
                :tid, :feedback, :seq, :elapsed,
                :created_at, :created_by
            )
            """,
            tid=task_eval_id,
            feedback=truncate(entry.get("feedback"), 4000),
            seq=entry.get("round"),
            elapsed=None,
            created_at=migration_time,
            created_by="migration",
        )
        count += 1
    return count


def insert_item_reviews(
    cur, task_eval_id: int, review_history: List[dict],
    rule_item_map: Dict[str, int],
    migration_time: datetime,
) -> Tuple[int, List[str]]:
    """review_history[*].issues → eval_task_result_item_review INSERT"""
    success = 0
    unmapped = []

    for entry in review_history:
        for issue in (entry.get("issues") or []):
            criterion = issue.get("criterion")
            eval_rule_item_id = rule_item_map.get(criterion)
            if eval_rule_item_id is None:
                unmapped.append(criterion)
                continue

            cur.execute(
                """
                INSERT INTO eval_task_result_item_review (
                    task_eval_id, eval_rule_item_id,
                    review, suggestion,
                    created_at, created_by
                ) VALUES (
                    :tid, :rid, :review, :suggestion,
                    :created_at, :created_by
                )
                """,
                tid=task_eval_id,
                rid=eval_rule_item_id,
                review=truncate(issue.get("reason"), 4000),
                suggestion=truncate(issue.get("suggestion"), 4000),
                created_at=migration_time,
                created_by="migration",
            )
            success += 1

    return success, unmapped


# ── 단일 key 마이그레이션 ───────────────────────────

def migrate_one(
    key_dir: Path,
    eval_rule_set_id: int,
    rule_item_map: Dict[str, int],
    model_name: str,
    migration_time: datetime,
) -> dict:
    """단일 key 디렉토리 마이그레이션"""
    key = key_dir.name
    meta_path = key_dir / "_meta.json"
    items_dir = key_dir / "items"

    if not meta_path.exists():
        return {"key": key, "status": "skipped", "error": "_meta.json 없음"}

    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        return {"key": key, "status": "failed", "error": f"_meta.json 로드 실패: {e}"}

    stage = "init"
    try:
        with db.cursor() as cur:
            stage = "lookup_task_id"
            task_id = lookup_task_id(cur, key)
            if task_id is None:
                return {"key": key, "status": "failed",
                        "error": f"task_id 조회 실패 (jira key {key} 없음)",
                        "stage": stage}

            eval_seq = meta.get("eval_seq", 1)

            stage = "delete_existing"
            deleted = delete_existing_result(cur, task_id, eval_rule_set_id, eval_seq)

            stage = "update_is_latest"
            cur.execute(
                """
                UPDATE eval_task_result
                SET is_latest = 'N'
                WHERE task_id = :tid AND eval_rule_set_id = :rsid
                """,
                tid=task_id, rsid=eval_rule_set_id,
            )

            stage = "insert_result"
            task_eval_id = insert_result(
                cur, task_id, eval_rule_set_id, meta,
                migration_time, model_name,
            )

            stage = "insert_result_items"
            item_count, unmapped_items = insert_result_items(
                cur, task_eval_id, items_dir, rule_item_map, migration_time,
            )

            review_history = meta.get("review_history") or []

            stage = "insert_result_reviews"
            review_count = insert_result_reviews(
                cur, task_eval_id, review_history, migration_time,
            )

            stage = "insert_item_reviews"
            item_review_count, unmapped_reviews = insert_item_reviews(
                cur, task_eval_id, review_history, rule_item_map, migration_time,
            )

        return {
            "key": key,
            "status": "ok",
            "task_eval_id": task_eval_id,
            "deleted_existing": deleted,
            "items": item_count,
            "reviews": review_count,
            "item_reviews": item_review_count,
            "unmapped_items": unmapped_items,
            "unmapped_review_criteria": unmapped_reviews,
        }
    except Exception as e:
        return {
            "key": key,
            "status": "failed",
            "error": str(e),
            "stage": stage,
        }


# ── 메인 ──────────────────────────────────────────

def migrate(
    storage_dir: Path,
    model_name: str,
    keys: Optional[List[str]] = None,
) -> None:
    final_dir = storage_dir / model_name / "final"
    if not final_dir.exists():
        print(f"[error] 디렉토리 없음: {final_dir}")
        sys.exit(1)

    rule_item_map, eval_rule_set_id = load_active_rule_items()
    print(f"[시작] model={model_name} | rule_set_id={eval_rule_set_id} | "
          f"활성 rule_items={len(rule_item_map)}개")

    if keys:
        key_dirs = []
        not_found = []
        for key in keys:
            kd = final_dir / key
            if kd.is_dir():
                key_dirs.append(kd)
            else:
                not_found.append(key)
        if not_found:
            print(f"  [warn] 디렉토리 없음: {not_found}")
        print(f"        지정 키 {len(key_dirs)}건")
    else:
        key_dirs = sorted([d for d in final_dir.iterdir() if d.is_dir()])
        print(f"        대상 {len(key_dirs)}건")

    if not key_dirs:
        print("\n  처리할 디렉토리 없음. 종료.")
        return

    print()
    migration_time = datetime.now()
    results = []

    for i, key_dir in enumerate(key_dirs, 1):
        result = migrate_one(
            key_dir, eval_rule_set_id, rule_item_map,
            model_name, migration_time,
        )
        results.append(result)

        prefix = f"  [{i}/{len(key_dirs)}] {result['key']}"
        if result["status"] == "ok":
            note = " (덮어쓰기)" if result.get("deleted_existing") else ""
            print(f"{prefix}: ✓ task_eval_id={result['task_eval_id']}{note} "
                  f"(items={result['items']}, reviews={result['reviews']}, "
                  f"item_reviews={result['item_reviews']})")
            if result.get("unmapped_items"):
                print(f"           [warn] 매핑 실패 items: {result['unmapped_items']}")
        elif result["status"] == "skipped":
            print(f"{prefix}: 스킵 - {result['error']}")
        else:
            stage = result.get("stage", "?")
            print(f"{prefix}: ✗ 실패 [{stage}] - {result['error']}")

    ok = sum(1 for r in results if r["status"] == "ok")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")

    print(f"\n{'='*50}")
    print(f"[결과] 전체={len(results)} | 성공={ok} | 스킵={skipped} | 실패={failed}")

    if failed > 0:
        print(f"\n[실패 목록]")
        for r in results:
            if r["status"] == "failed":
                stage = r.get("stage", "?")
                print(f"  - {r['key']} [{stage}]: {r['error']}")


# ── 유틸 ─────────────────────────────────────────

def _score_from_pass_fail(pass_fail: str) -> float:
    return {"PASS": 1.0, "PARTIAL": 0.5, "FAIL": 0.0}.get(pass_fail, 0.0)


def _pass_yn(pass_fail: str) -> str:
    return "Y" if pass_fail == "PASS" else "N"


def _grade_from_status(status: Optional[str]) -> Optional[str]:
    """supervisor.status → grade_code 매핑"""
    if status == "approved":
        return "APPROVED"
    if status == "not_approved":
        return "NOT_APPRV"
    if status == "supervisor_failed":
        return "SUP_FAIL"
    return None
