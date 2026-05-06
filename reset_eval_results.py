"""
평가 결과 테이블 리셋 스크립트.

[삭제 대상]
- eval_task_result_item_review (자식 - 지적사항)
- eval_task_result_review      (자식 - 라운드별 피드백)
- eval_task_result_item        (자식 - 항목별 결과)
- eval_task_result             (부모 - 메타)

[필터 조건]
- eval_rule_set_id 기준
- 옵션: model_name 추가 필터
- 옵션: created_by 추가 필터

[안전장치]
- 기본은 dry-run (실제 삭제 안함)
- --execute 플래그를 명시해야 실제 삭제
- 삭제 전 영향 범위 미리보기 (예: 어떤 task, 몇 건)

[사용법]
# 미리보기 (기본)
python reset_eval_results.py --rule-set-id 22

# 모델 필터 추가
python reset_eval_results.py --rule-set-id 22 --model-name Qwen3.6-27B

# 실제 실행
python reset_eval_results.py --rule-set-id 22 --execute
"""

import argparse
import sys
from typing import List, Optional

from common import db


# ── 영향 범위 조회 ──────────────────────────────────

def fetch_target_results(
    eval_rule_set_id: int,
    model_name: Optional[str] = None,
    created_by: Optional[str] = None,
) -> List[dict]:
    """삭제 대상 task_eval_id 목록 조회"""
    where = ["eval_rule_set_id = :rsid"]
    params = {"rsid": eval_rule_set_id}

    if model_name:
        where.append("model_name = :mname")
        params["mname"] = model_name

    if created_by:
        where.append("created_by = :cby")
        params["cby"] = created_by

    sql = f"""
        SELECT task_eval_id, task_id, eval_seq, model_name, 
               created_by, evaluated_at
        FROM eval_task_result
        WHERE {' AND '.join(where)}
        ORDER BY task_eval_id
    """
    return db.select(sql, **params)


def count_children(task_eval_ids: List[int]) -> dict:
    """삭제 대상 자식 테이블 행 수 카운트"""
    if not task_eval_ids:
        return {
            "eval_task_result_item": 0,
            "eval_task_result_review": 0,
            "eval_task_result_item_review": 0,
        }

    counts = {}
    # 청크로 나눠서 IN절 처리
    for chunk_start in range(0, len(task_eval_ids), 500):
        chunk = task_eval_ids[chunk_start: chunk_start + 500]
        placeholders = ", ".join(f":id{i}" for i in range(len(chunk)))
        params = {f"id{i}": tid for i, tid in enumerate(chunk)}

        # eval_task_result_item
        row = db.fetch(
            f"SELECT COUNT(*) AS cnt FROM eval_task_result_item "
            f"WHERE task_eval_id IN ({placeholders})",
            **params,
        )
        counts["eval_task_result_item"] = counts.get("eval_task_result_item", 0) + row["cnt"]

        # eval_task_result_review
        row = db.fetch(
            f"SELECT COUNT(*) AS cnt FROM eval_task_result_review "
            f"WHERE task_eval_result_id IN ({placeholders})",
            **params,
        )
        counts["eval_task_result_review"] = counts.get("eval_task_result_review", 0) + row["cnt"]

        # eval_task_result_item_review
        row = db.fetch(
            f"SELECT COUNT(*) AS cnt FROM eval_task_result_item_review "
            f"WHERE task_eval_id IN ({placeholders})",
            **params,
        )
        counts["eval_task_result_item_review"] = counts.get("eval_task_result_item_review", 0) + row["cnt"]

    return counts


# ── 삭제 실행 ──────────────────────────────────────

def delete_targets(task_eval_ids: List[int]) -> dict:
    """자식 → 부모 순으로 삭제"""
    deleted = {
        "eval_task_result_item_review": 0,
        "eval_task_result_review": 0,
        "eval_task_result_item": 0,
        "eval_task_result": 0,
    }

    if not task_eval_ids:
        return deleted

    with db.cursor() as cur:
        # 청크별 삭제
        for chunk_start in range(0, len(task_eval_ids), 500):
            chunk = task_eval_ids[chunk_start: chunk_start + 500]
            placeholders = ", ".join(f":id{i}" for i in range(len(chunk)))
            params = {f"id{i}": tid for i, tid in enumerate(chunk)}

            # 1. eval_task_result_item_review
            cur.execute(
                f"DELETE FROM eval_task_result_item_review "
                f"WHERE task_eval_id IN ({placeholders})",
                **params,
            )
            deleted["eval_task_result_item_review"] += cur.rowcount

            # 2. eval_task_result_review
            cur.execute(
                f"DELETE FROM eval_task_result_review "
                f"WHERE task_eval_result_id IN ({placeholders})",
                **params,
            )
            deleted["eval_task_result_review"] += cur.rowcount

            # 3. eval_task_result_item
            cur.execute(
                f"DELETE FROM eval_task_result_item "
                f"WHERE task_eval_id IN ({placeholders})",
                **params,
            )
            deleted["eval_task_result_item"] += cur.rowcount

            # 4. eval_task_result (부모)
            cur.execute(
                f"DELETE FROM eval_task_result "
                f"WHERE task_eval_id IN ({placeholders})",
                **params,
            )
            deleted["eval_task_result"] += cur.rowcount

    return deleted


# ── 메인 ──────────────────────────────────────────

def run(
    eval_rule_set_id: int,
    model_name: Optional[str],
    created_by: Optional[str],
    execute: bool,
):
    # 1. 영향 범위 조회
    print(f"[조회] eval_rule_set_id={eval_rule_set_id}", end="")
    if model_name:
        print(f" | model_name={model_name}", end="")
    if created_by:
        print(f" | created_by={created_by}", end="")
    print()

    targets = fetch_target_results(eval_rule_set_id, model_name, created_by)

    if not targets:
        print("\n  삭제 대상 없음. 종료.")
        return

    task_eval_ids = [r["task_eval_id"] for r in targets]
    child_counts = count_children(task_eval_ids)

    # 2. 영향 범위 출력
    print(f"\n[영향 범위]")
    print(f"  - eval_task_result            : {len(targets):>6}건")
    print(f"  - eval_task_result_item       : {child_counts['eval_task_result_item']:>6}건")
    print(f"  - eval_task_result_review     : {child_counts['eval_task_result_review']:>6}건")
    print(f"  - eval_task_result_item_review: {child_counts['eval_task_result_item_review']:>6}건")
    total = (len(targets)
             + child_counts['eval_task_result_item']
             + child_counts['eval_task_result_review']
             + child_counts['eval_task_result_item_review'])
    print(f"  {'─'*42}")
    print(f"  합계: {total:>6}건")

    # 3. 샘플 (최대 10개)
    print(f"\n[삭제 대상 샘플 (최대 10건)]")
    for r in targets[:10]:
        print(f"  - task_eval_id={r['task_eval_id']:>5} | "
              f"task_id={r['task_id']:>5} | seq={r['eval_seq']} | "
              f"model={r['model_name']} | by={r['created_by']}")
    if len(targets) > 10:
        print(f"  ... 외 {len(targets) - 10}건")

    # 4. 실행 또는 미리보기
    if not execute:
        print(f"\n[DRY-RUN] 실제 삭제는 수행하지 않음.")
        print(f"          실제 삭제하려면 --execute 옵션 추가.")
        return

    # 확인 입력
    print(f"\n[!] 위 내용을 실제로 삭제합니다.")
    confirm = input("    계속하려면 'DELETE' 입력: ").strip()
    if confirm != "DELETE":
        print("    취소됨.")
        return

    # 실제 삭제
    print(f"\n[삭제 실행]")
    deleted = delete_targets(task_eval_ids)
    print(f"  - eval_task_result_item_review: {deleted['eval_task_result_item_review']:>6}건 삭제")
    print(f"  - eval_task_result_review     : {deleted['eval_task_result_review']:>6}건 삭제")
    print(f"  - eval_task_result_item       : {deleted['eval_task_result_item']:>6}건 삭제")
    print(f"  - eval_task_result            : {deleted['eval_task_result']:>6}건 삭제")
    print(f"\n[완료]")


# ── CLI ──────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="평가 결과 테이블 리셋 스크립트 (자식 4 → 부모 1 순)",
    )
    parser.add_argument(
        "--rule-set-id", type=int, required=True,
        help="삭제 대상 eval_rule_set_id (필수)",
    )
    parser.add_argument(
        "--model-name", default=None,
        help="추가 필터: 특정 model_name만",
    )
    parser.add_argument(
        "--created-by", default=None,
        help="추가 필터: 특정 created_by만 (예: migration)",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="실제 삭제 실행 (없으면 dry-run)",
    )
    args = parser.parse_args()

    run(
        eval_rule_set_id=args.rule_set_id,
        model_name=args.model_name,
        created_by=args.created_by,
        execute=args.execute,
    )
