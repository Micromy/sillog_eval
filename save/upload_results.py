# -*- coding: utf-8 -*-
"""Task: 평가 결과(JSON) → eval_task_result* DB 마이그레이션.

호출 예:
    python run_task.py save upload_results <model_name>
    python run_task.py save upload_results <model_name> --keys SOCCHIP-102 SOCIP-742
"""
import argparse
from pathlib import Path

from common.config import STORAGE_DIR
from common.db.result import migrate


def run() -> None:
    parser = argparse.ArgumentParser(description="평가 결과 DB 마이그레이션")
    parser.add_argument("model_name", help="모델명 (final 하위 폴더명)")
    parser.add_argument("--storage-dir", default=STORAGE_DIR,
                        help=f"저장 루트 (기본값: {STORAGE_DIR})")
    parser.add_argument("--keys", nargs="+", default=None,
                        help="특정 키만 처리 (공백 구분)")
    parser.add_argument("--keys-file", default=None,
                        help="키 목록 파일 (한 줄에 하나, --keys와 함께 사용 가능)")
    args = parser.parse_args()

    keys: list = []
    if args.keys:
        keys.extend(args.keys)
    if args.keys_file:
        with open(args.keys_file, encoding="utf-8") as f:
            keys.extend(
                line.strip() for line in f
                if line.strip() and not line.startswith("#")
            )

    migrate(
        storage_dir=Path(args.storage_dir),
        model_name=args.model_name,
        keys=keys if keys else None,
    )


if __name__ == "__main__":
    run()
