# -*- coding: utf-8 -*-
"""Task: STORAGE_DIR의 잔존 로컬 파일 정리.

새 파이프라인은 결과를 DB에 직접 저장하므로 로컬에는 jira_issues.pkl 정도만
남는다. 옛 버전의 잔존 디렉토리(parsed/, {model}/final, {model}/iteration)도
함께 정리.

호출 예:
    python run_task.py cleanup cleanup_files               # pkl 포함 정리
    python run_task.py cleanup cleanup_files --keep-pkl    # pkl 보존
    python run_task.py cleanup cleanup_files --dry-run     # 미리보기
"""
import argparse

from common.cleanup import cleanup_storage


def run() -> None:
    parser = argparse.ArgumentParser(description="cleanup cleanup_files")
    parser.add_argument("--keep-pkl", action="store_true",
                        help="jira_issues.pkl 보존 (기본: 삭제)")
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 삭제 없이 대상만 출력")
    args = parser.parse_args()

    cleanup_storage(keep_pkl=args.keep_pkl, dry_run=args.dry_run)


if __name__ == "__main__":
    run()
