# -*- coding: utf-8 -*-
"""
로컬 parsed JSON → eval_task_parsed 일괄 적재 스크립트.

사용법:
    python upload_parsed.py [--run-id RUN_ID] [--parser-version VER] [--dry-run]
    python upload_parsed.py --parsed-dir /custom/path

경로:
    기본값은 config.STORAGE_DIR/parsed/ 에서 읽음.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from common import db
from config import STORAGE_DIR
from parser.persistence import save_parsed


PARSED_SUBDIR = "parsed"


def discover_files(parsed_dir: Path) -> list[Path]:
    """디렉터리에서 {key}.json 파일 목록 수집."""
    if not parsed_dir.exists():
        print(f"[ERROR] 디렉터리 없음: {parsed_dir}")
        sys.exit(1)

    files = sorted(parsed_dir.glob("*.json"))
    if not files:
        print(f"[WARN] JSON 파일 없음: {parsed_dir}")
        sys.exit(0)

    return files


def extract_key(filepath: Path) -> str:
    """파일명에서 이슈 키 추출. 예: PROJ-1234.json → PROJ-1234"""
    return filepath.stem


def load_json(filepath: Path) -> dict:
    """JSON 파일 로드."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_sillog_structure(data: dict, key: str) -> list[str]:
    """최소 구조 검증. 에러 메시지 리스트 반환 (빈 리스트 = 정상)."""
    errors = []

    if "description" not in data:
        errors.append("description 필드 없음")
    else:
        desc = data["description"]
        if "purpose" not in desc:
            errors.append("description.purpose 필드 없음")
        if "input_data" not in desc:
            errors.append("description.input_data 필드 없음")

    if "checklist" not in data:
        errors.append("checklist 필드 없음")

    if "outputs" not in data:
        errors.append("outputs 필드 없음")

    return errors


def run(
    parsed_dir: Path,
    run_id: str,
    parser_version: str,
    dry_run: bool = False,
):
    all_files = discover_files(parsed_dir)
    files = [f for f in all_files if not f.name.startswith("_load_errors_")]
    excluded = len(all_files) - len(files)

    print(f"[시작] {len(files)}개 파일 발견 | run_id={run_id} | parser_version={parser_version}")
    if excluded:
        print(f"  (에러 로그 파일 {excluded}개 제외)")
    if dry_run:
        print("[DRY-RUN] DB 적재 없이 검증만 수행합니다.\n")

    success = 0
    skipped = 0
    failed = 0
    errors_log = []

    for i, filepath in enumerate(files, 1):
        key = extract_key(filepath)
        prefix = f"  [{i}/{len(files)}] {key}"

        try:
            data = load_json(filepath)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"{prefix}: JSON 파싱 실패 - {e}")
            errors_log.append({"key": key, "error": f"JSON 파싱 실패: {e}"})
            failed += 1
            continue

        validation_errors = validate_sillog_structure(data, key)
        warning_msg = ""
        if validation_errors:
            warning_msg = f" [구조 부족: {'; '.join(validation_errors)}]"

        if dry_run:
            desc = data.get("description", {}) or {}
            input_count = len(desc.get("input_data") or [])
            output_count = len(data.get("outputs") or [])
            check_count = len(data.get("checklist") or [])
            print(f"{prefix}: OK (input={input_count}, output={output_count}, check={check_count}){warning_msg}")
            success += 1
            continue

        try:
            parsed_id = save_parsed(
                run_id=run_id,
                source_issue_key=key,
                sillog_data=data,
                parser_version=parser_version,
            )
            print(f"{prefix}: 적재 완료 → parsed_id={parsed_id}{warning_msg}")
            success += 1
        except Exception as e:
            error_msg = str(e)
            if "uk_parsed" in error_msg.lower() or "unique constraint" in error_msg.lower():
                print(f"{prefix}: 이미 적재됨 (skip)")
                skipped += 1
            else:
                print(f"{prefix}: 적재 실패 - {error_msg}")
                errors_log.append({"key": key, "error": error_msg})
                failed += 1

    print(f"\n{'='*50}")
    print(f"[결과] 전체={len(files)} | 성공={success} | 스킵={skipped} | 실패={failed}")

    if errors_log:
        print(f"\n[실패 목록]")
        for err in errors_log:
            print(f"  - {err['key']}: {err['error']}")

        error_log_path = parsed_dir / f"_load_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(error_log_path, "w", encoding="utf-8") as f:
            json.dump(errors_log, f, ensure_ascii=False, indent=2)
        print(f"\n  에러 로그 저장: {error_log_path}")

    return success, skipped, failed


def main():
    default_parsed_dir = str(Path(STORAGE_DIR) / PARSED_SUBDIR)

    parser = argparse.ArgumentParser(
        description="로컬 parsed JSON 파일을 eval_task_parsed 테이블로 적재"
    )
    parser.add_argument(
        "--parsed-dir",
        type=str,
        default=default_parsed_dir,
        help=f"parsed JSON 디렉터리 (기본값: config → {default_parsed_dir})",
    )
    parser.add_argument(
        "--run-id",
        default=f"migrate_{datetime.now().strftime('%Y%m%d')}",
        help="run_id (기본값: migrate_YYYYMMDD)",
    )
    parser.add_argument(
        "--parser-version",
        default="SilLog-Vanguard",
        help="parser_version (기본값: SilLog-Vanguard)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB 적재 없이 파일 검증만 수행",
    )

    args = parser.parse_args()
    parsed_dir = Path(args.parsed_dir)

    print(f"[경로] {parsed_dir}")
    run(
        parsed_dir=parsed_dir,
        run_id=args.run_id,
        parser_version=args.parser_version,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
