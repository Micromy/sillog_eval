# -*- coding: utf-8 -*-
"""Task: Jira에서 이슈를 fetch해 jira_issues.pkl로 저장.

[옵션]
- 기본: FILTER_ID env로 저장된 Jira filter의 JQL을 가져와 호출. 캐시 존재 시 skip.
- `--jql "key in (PROJ-1, PROJ-2)"`: FILTER_ID 무시하고 JQL 직접 사용. 캐시 덮어씀.
  테스트나 임시 조회에 편리.
"""
import argparse

from common.config import FILTER_ID, STORAGE_DIR
from common.constants import JIRA_CACHE_FILENAME
from common.jira.client import get_jql_filter, get_sections_by_key
from common.storage import save_pkl


def run() -> None:
    parser = argparse.ArgumentParser(description="parse fetch_jira")
    parser.add_argument("--jql", default=None,
                        help="JQL 직접 지정 (지정 시 FILTER_ID 무시, 캐시 덮어쓰고 fetch)")
    args = parser.parse_args()

    sections_file_path = STORAGE_DIR / JIRA_CACHE_FILENAME

    if args.jql:
        jql = args.jql
        print(f"[fetch_jira] --jql 직접 지정: {jql}")
    else:
        if sections_file_path.exists():
            print(f"[fetch_jira] 캐시 존재, 스킵: {sections_file_path}")
            return
        jql = get_jql_filter(FILTER_ID)

    issues_by_key = get_sections_by_key(jql)
    save_pkl(sections_file_path, issues_by_key)
    print(f"[fetch_jira] {len(issues_by_key)}건 저장 → {sections_file_path}")


if __name__ == "__main__":
    run()
