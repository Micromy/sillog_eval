# -*- coding: utf-8 -*-
"""Task: 로컬 parsed JSON → eval_task_parsed* DB 일괄 적재.

호출 예:
    python run_task.py save upload_parsed --dry-run
    python run_task.py save upload_parsed --run-id my_run --parser-version v2
    python run_task.py save upload_parsed --parsed-dir /custom/path
"""
import argparse
from datetime import datetime
from pathlib import Path

from common.config import STORAGE_DIR
from common.db.parsed import upload


PARSED_SUBDIR = "parsed"


def run() -> None:
    default_parsed_dir = str(Path(STORAGE_DIR) / PARSED_SUBDIR)

    parser = argparse.ArgumentParser(
        description="로컬 parsed JSON 파일을 eval_task_parsed 테이블로 적재"
    )
    parser.add_argument("--parsed-dir", type=str, default=default_parsed_dir,
                        help=f"parsed JSON 디렉터리 (기본값: {default_parsed_dir})")
    parser.add_argument("--run-id", default=f"migrate_{datetime.now().strftime('%Y%m%d')}",
                        help="run_id (기본값: migrate_YYYYMMDD)")
    parser.add_argument("--parser-version", default="SilLog-Vanguard",
                        help="parser_version (기본값: SilLog-Vanguard)")
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 적재 없이 파일 검증만 수행")
    args = parser.parse_args()

    parsed_dir = Path(args.parsed_dir)
    print(f"[경로] {parsed_dir}")
    upload(
        parsed_dir=parsed_dir,
        run_id=args.run_id,
        parser_version=args.parser_version,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    run()
