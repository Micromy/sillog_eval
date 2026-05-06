# -*- coding: utf-8 -*-
"""Task: Jira에서 이슈를 fetch해 jira_issues.pkl로 저장.

이전 단계의 캐시가 있으면 그대로 사용 (idempotent).
"""
from common.config import FILTER_ID, STORAGE_DIR
from common.storage import save_pkl
from common.jira.client import get_jql_filter, get_sections_by_key


def run() -> None:
    sections_file_path = STORAGE_DIR / "jira_issues.pkl"
    if sections_file_path.exists():
        print(f"[fetch_jira] 캐시 존재, 스킵: {sections_file_path}")
        return

    jql = get_jql_filter(FILTER_ID)
    issues_by_key = get_sections_by_key(jql)
    save_pkl(sections_file_path, issues_by_key)
    print(f"[fetch_jira] {len(issues_by_key)}건 저장 → {sections_file_path}")


if __name__ == "__main__":
    run()
