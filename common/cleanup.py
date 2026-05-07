# -*- coding: utf-8 -*-
"""STORAGE_DIR 안의 잔존 로컬 파일 정리.

새 파이프라인은 모든 결과를 DB에 저장하므로 로컬 파일은 사실상 `jira_issues.pkl`
(Jira fetch 캐시) 외에는 만들지 않는다. 이 모듈은:
- jira_issues.pkl 삭제 (옵션 제어)
- 옛 버전에서 남았을 가능성이 있는 디렉토리(parsed/, {model}/final/, {model}/iteration/) 정리
"""
import shutil
from pathlib import Path

from common.config import STORAGE_DIR
from common.constants import (
    FINAL_SUBDIR,
    ITERATION_SUBDIR,
    JIRA_CACHE_FILENAME,
    PARSED_SUBDIR,
)


def cleanup_storage(keep_pkl: bool = False, dry_run: bool = False) -> None:
    """STORAGE_DIR 안의 잔존 파일/디렉토리 정리.

    Args:
        keep_pkl: True면 jira_issues.pkl 보존, False면 삭제.
        dry_run: True면 실제 삭제 없이 대상만 출력.
    """
    storage = Path(STORAGE_DIR)
    print(f"[cleanup] storage_dir={storage} | keep_pkl={keep_pkl} | dry_run={dry_run}")

    if not storage.exists():
        print("  STORAGE_DIR 자체가 없음. 종료.")
        return

    targets: list[tuple[str, Path, bool]] = []  # (label, path, is_dir)

    # 1. jira_issues.pkl
    pkl_path = storage / JIRA_CACHE_FILENAME
    if pkl_path.exists() and not keep_pkl:
        targets.append(("jira fetch 캐시", pkl_path, False))

    # 2. 옛 디렉토리 (이전 버전의 parsed/ 결과 파일)
    parsed_dir = storage / PARSED_SUBDIR
    if parsed_dir.exists():
        targets.append(("옛 parsed/ 디렉토리", parsed_dir, True))

    # 3. 옛 model 디렉토리들 (final/, iteration/)
    for model_dir in storage.iterdir() if storage.is_dir() else []:
        if not model_dir.is_dir():
            continue
        if model_dir.name == PARSED_SUBDIR:
            continue  # 위에서 이미 처리
        for sub in (FINAL_SUBDIR, ITERATION_SUBDIR):
            sub_dir = model_dir / sub
            if sub_dir.exists():
                targets.append((f"옛 {model_dir.name}/{sub}/ 디렉토리", sub_dir, True))

    if not targets:
        print("  정리할 대상 없음.")
        return

    print(f"\n[정리 대상 {len(targets)}건]")
    for label, path, is_dir in targets:
        kind = "디렉토리" if is_dir else "파일"
        print(f"  - {label} ({kind}): {path}")

    if dry_run:
        print("\n[DRY-RUN] 실제 삭제는 수행하지 않음.")
        return

    print("\n[삭제 실행]")
    for label, path, is_dir in targets:
        try:
            if is_dir:
                shutil.rmtree(path)
            else:
                path.unlink()
            print(f"  ✓ {path}")
        except Exception as e:
            print(f"  ✗ {path} - {e}")

    print("\n[완료]")
