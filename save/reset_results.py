# -*- coding: utf-8 -*-
"""Task: 평가 결과 테이블 리셋 (eval_task_result* 자식 4 → 부모 1 순 삭제).

호출 예:
    python run_task.py save reset_results --rule-set-id 22                # dry-run
    python run_task.py save reset_results --rule-set-id 22 --execute      # 실삭제
    python run_task.py save reset_results --rule-set-id 22 --model-name Qwen3.6-27B
"""
import argparse

from common.db.reset import reset


def run() -> None:
    parser = argparse.ArgumentParser(
        description="평가 결과 테이블 리셋 (자식 4 → 부모 1 순)",
    )
    parser.add_argument("--rule-set-id", type=int, required=True,
                        help="삭제 대상 eval_rule_set_id (필수)")
    parser.add_argument("--model-name", default=None,
                        help="추가 필터: 특정 model_name만")
    parser.add_argument("--created-by", default=None,
                        help="추가 필터: 특정 created_by만 (예: migration)")
    parser.add_argument("--execute", action="store_true",
                        help="실제 삭제 실행 (없으면 dry-run)")
    args = parser.parse_args()

    reset(
        eval_rule_set_id=args.rule_set_id,
        model_name=args.model_name,
        created_by=args.created_by,
        execute=args.execute,
    )


if __name__ == "__main__":
    run()
