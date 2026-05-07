# -*- coding: utf-8 -*-
"""Task: DB의 parsed 결과(status='DONE')를 일괄 평가.

선행 task: parse parse_description (eval_task_parsed*에 status='DONE' row 생성).

[재개]
같은 --run-id / --eval-rule-set-id 조합으로 재호출하면 DB의 status='DONE'인
task_id를 skip. 중간에 sys.exit(2)로 셧다운된 경우 PENDING row만 다음 호출에서 재처리.
"""
import argparse
import json
import sys

from common import db
from common.config import (
    PLATFORM,
    DTGPT_MODEL,
    DS_LLM_MODEL,
    LLM_POOL_SIZE,
)
from common.constants import Status
from common.db.result import get_done_task_ids
from common.llm import create_llm
from common.scoring.scorer import score_issues_batch


def run() -> None:
    parser = argparse.ArgumentParser(description="score score_issues")
    parser.add_argument("--run-id", required=True,
                        help="parse 실행 ID — eval_task_parsed에서 같은 run_id의 DONE row를 평가 대상으로")
    parser.add_argument("--eval-rule-set-id", type=int, required=True,
                        help="활성 eval_rule_set_id (eval_task_result에 기록될 값)")
    parser.add_argument("--eval-seq", type=int, default=1,
                        help="eval_seq (기본 1, 재평가 시 caller가 명시)")
    args = parser.parse_args()

    # 1. parsed 결과 로드 (DB에서, 로컬 파일 X)
    rows = db.select(
        """
        SELECT task_id, source_issue_key, raw_json
        FROM eval_task_parsed
        WHERE run_id = :rid
          AND status = :status
          AND task_id IS NOT NULL
        """,
        rid=args.run_id,
        status=Status.DONE,
    )

    if not rows:
        print(f"[score_issues] run_id={args.run_id} 에 DONE 상태 parsed 데이터 없음. "
              f"먼저 parse parse_description 실행 필요.", file=sys.stderr)
        sys.exit(1)

    # 2. 이미 score DONE인 task_id skip
    done_task_ids = get_done_task_ids(args.eval_rule_set_id, args.eval_seq)
    pending = [r for r in rows if r["task_id"] not in done_task_ids]

    print(f"[score_issues] parsed {len(rows)}건 / 이미 평가 완료 {len(done_task_ids)}건 / 대상 {len(pending)}건")
    if not pending:
        print("  처리할 이슈 없음. 종료.")
        return

    items = [(r["source_issue_key"], json.loads(r["raw_json"])) for r in pending]

    model_name = DTGPT_MODEL if PLATFORM == 'DTGPT' else DS_LLM_MODEL if PLATFORM == 'DS_LLM' else ""
    llm_pool = [create_llm() for _ in range(LLM_POOL_SIZE)]

    results = score_issues_batch(
        items=items,
        llm_pool=llm_pool,
        model_name=model_name,
        run_id=args.run_id,
        eval_rule_set_id=args.eval_rule_set_id,
        eval_seq=args.eval_seq,
    )
    print(f"[score_issues] {len(results)}건 평가 완료 (model={model_name})")


if __name__ == "__main__":
    run()
