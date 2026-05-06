# -*- coding: utf-8 -*-
"""Task: parsed/*.json을 일괄 평가.

선행 task: parse_description (parsed/{key}.json 생성).
"""
import json
import sys

from common.config import (
    PLATFORM,
    DTGPT_MODEL,
    DS_LLM_MODEL,
    LLM_POOL_SIZE,
    STORAGE_DIR,
)
from common.llm import create_llm
from score.scorer import score_issues_batch


def run() -> None:
    parsed_dir = STORAGE_DIR / "parsed"
    if not parsed_dir.exists():
        print(f"[score_issues] {parsed_dir} 없음. 먼저 parse_description 실행 필요.", file=sys.stderr)
        sys.exit(1)

    items = []
    for fp in sorted(parsed_dir.glob("*.json")):
        if fp.name.startswith("_"):
            continue  # 에러 로그 파일 제외
        with open(fp, encoding="utf-8") as f:
            items.append((fp.stem, json.load(f)))

    if not items:
        print(f"[score_issues] 파싱 결과 없음: {parsed_dir}", file=sys.stderr)
        sys.exit(1)

    model_name = DTGPT_MODEL if PLATFORM == 'DTGPT' else DS_LLM_MODEL if PLATFORM == 'DS_LLM' else ""
    llm_pool = [create_llm() for _ in range(LLM_POOL_SIZE)]

    results = score_issues_batch(items=items, llm_pool=llm_pool, model_name=model_name)
    print(f"[score_issues] {len(results)}건 평가 완료 (model={model_name})")


if __name__ == "__main__":
    run()
