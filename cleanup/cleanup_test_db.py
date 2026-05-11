# -*- coding: utf-8 -*-
"""Task: 테스트 데이터 DB 정리.

특정 run_id prefix(예: `test_`)로 적재된 eval_task_parsed* + 연결된 eval_task_result*
모두 자식 → 부모 순으로 삭제. 테스트 후 운영 데이터에 영향 없이 정리하기 위함.

[안전장치]
- 기본 dry-run (영향 범위만 출력)
- `--execute` 명시 + 'DELETE' 확인 입력해야 실삭제
- run_id_prefix 최소 3자 이상 (실수 방지)

호출 예:
    python run_task.py cleanup cleanup_test_db --run-id-prefix test_              # dry-run
    python run_task.py cleanup cleanup_test_db --run-id-prefix test_ --execute   # 실삭제
    python run_task.py cleanup cleanup_test_db --run-id-prefix test_20260511     # 특정 run만
"""
import argparse
import sys

from common.db.cleanup import cleanup_test_db


def run() -> None:
    parser = argparse.ArgumentParser(
        description="테스트 데이터 DB 정리 (eval_task_parsed* + eval_task_result*)",
    )
    parser.add_argument("--run-id-prefix", required=True,
                        help="삭제 대상 run_id LIKE 접두 (예: 'test_'). 최소 3자")
    parser.add_argument("--execute", action="store_true",
                        help="실제 삭제 실행 (없으면 dry-run)")
    parser.add_argument("--yes", action="store_true",
                        help="실삭제 시 'DELETE' 확인 입력 생략 (스크립트용)")
    args = parser.parse_args()

    if args.execute and not args.yes:
        print(f"\n[!] run_id LIKE '{args.run_id_prefix}%' 인 데이터를 실삭제합니다.")
        confirm = input("    계속하려면 'DELETE' 입력: ").strip()
        if confirm != "DELETE":
            print("    취소됨.")
            sys.exit(1)

    cleanup_test_db(
        run_id_prefix=args.run_id_prefix,
        execute=args.execute,
    )


if __name__ == "__main__":
    run()
