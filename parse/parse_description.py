# -*- coding: utf-8 -*-
"""Task: jira_issues.pkl을 LLM 파싱하여 parsed/{key}.json으로 저장.

선행 task: fetch_jira (jira_issues.pkl 생성).
실패 키에 대해 최대 3회 재시도.
"""
import sys

from common.config import LLM_POOL_SIZE, STORAGE_DIR
from common.llm import create_llm
from common.storage import load_pkl
from parse.llm_parser import parse_issues_parallel


def run() -> None:
    sections_file_path = STORAGE_DIR / "jira_issues.pkl"
    if not sections_file_path.exists():
        print(f"[parse_description] {sections_file_path} 없음. 먼저 fetch_jira 실행 필요.", file=sys.stderr)
        sys.exit(1)

    issues_by_key = load_pkl(sections_file_path)
    llm_pools = [create_llm() for _ in range(LLM_POOL_SIZE)]

    parsed_issues: dict = {}
    remaining = issues_by_key
    for attempt in range(3):
        if not remaining:
            break
        new_parsed, failed_keys = parse_issues_parallel(
            issues_by_key=remaining,
            llm_pools=llm_pools,
        )
        parsed_issues.update(new_parsed)
        remaining = {k: issues_by_key[k] for k in failed_keys}

    final_failed = list(remaining.keys())
    print(f"[parse_description] 성공 {len(parsed_issues)}건 / 최종 실패 {len(final_failed)}건")
    if final_failed:
        print(f"  실패 키: {final_failed}")


if __name__ == "__main__":
    run()
