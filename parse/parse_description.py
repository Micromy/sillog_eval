# -*- coding: utf-8 -*-
"""Task: jira_issues.pkl을 LLM 파싱하여 eval_task_parsed* DB로 직접 적재.

선행 task: parse fetch_jira (jira_issues.pkl 생성).

[재개]
같은 --run-id로 재호출하면 DB의 status='DONE'인 source_issue_key를 skip.
중간에 sys.exit(2)로 셧다운된 경우 PENDING row만 다음 호출에서 재처리.
"""
import argparse
import sys

from common.config import LLM_POOL_SIZE, STORAGE_DIR
from common.constants import JIRA_CACHE_FILENAME
from common.db.parsed import get_done_keys
from common.llm import create_llm
from common.storage import load_pkl
from common.jira.llm_parser import parse_issues_parallel


def run() -> None:
    parser = argparse.ArgumentParser(description="parse parse_description")
    parser.add_argument("--run-id", required=True,
                        help="parse 실행 ID (재개 시 같은 값으로 재호출)")
    parser.add_argument("--parser-version", default="SilLog-Vanguard",
                        help="parser_version (기본값: SilLog-Vanguard)")
    args = parser.parse_args()

    sections_file_path = STORAGE_DIR / JIRA_CACHE_FILENAME
    if not sections_file_path.exists():
        print(f"[parse_description] {sections_file_path} 없음. 먼저 parse fetch_jira 실행 필요.",
              file=sys.stderr)
        sys.exit(1)

    issues_by_key = load_pkl(sections_file_path)
    done_keys = get_done_keys(args.run_id)
    pending = {k: v for k, v in issues_by_key.items() if k not in done_keys}

    print(f"[parse_description] 전체 {len(issues_by_key)}건 / 완료 {len(done_keys)}건 / 대상 {len(pending)}건")
    if not pending:
        print("  처리할 이슈 없음. 종료.")
        return

    llm_pools = [create_llm() for _ in range(LLM_POOL_SIZE)]

    success, failed = parse_issues_parallel(
        issues_by_key=pending,
        llm_pools=llm_pools,
        run_id=args.run_id,
        parser_version=args.parser_version,
    )

    print(f"[parse_description] 성공 {success} / 실패 {failed}")


if __name__ == "__main__":
    run()
