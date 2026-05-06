# -*- coding: utf-8 -*-
"""Task: _meta.json 포맷 마이그레이션 (legacy → summary 필드 백필).

호출 예:
    python run_task.py save migrate_meta <storage_dir>
    python run_task.py save migrate_meta <storage_dir> --model gauss-v1
    python run_task.py save migrate_meta <storage_dir> --dry-run
"""
import argparse
from pathlib import Path

from common.db.meta import migrate_all


def run() -> None:
    parser = argparse.ArgumentParser(description="_meta.json 마이그레이션")
    parser.add_argument("storage_dir", help="저장 루트 디렉토리 (예: eval_results)")
    parser.add_argument("--model", default=None, help="특정 모델만 처리")
    parser.add_argument("--dry-run", action="store_true", help="실제 변경 없이 미리보기")
    args = parser.parse_args()

    migrate_all(
        storage_dir=Path(args.storage_dir),
        model_filter=args.model,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    run()
