# -*- coding: utf-8 -*-
"""LLM 병렬 파싱 (Jira sections → SillogData) + DB 직접 적재.

각 issue마다:
1. eval_task_parsed에 placeholder 1행 INSERT (status='PENDING')
2. LLM 호출 (safe_structured_invoke 내부에서 retry 3회)
3-A. 성공: populate_parsed로 본문 + 자식 INSERT + status='DONE'
3-B. 실패: mark_parsed_failed로 status='FAILED' + failed_reason

retry까지 실패한 issue가 누적 SHUTDOWN_THRESHOLD에 도달하면
서버 다운 가능성으로 보고 sys.exit(2).
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import db
from common.config import PARSING_TEMPLATE, SHUTDOWN_THRESHOLD
from common.db.parsed import (
    insert_parsed_placeholder,
    mark_parsed_failed,
    populate_parsed,
)
from common.llm import safe_structured_invoke
from common.shutdown import FailureCounter
from .models import SillogData


def parse_issues_parallel(
    issues_by_key: dict[str, dict[str, str]],
    llm_pools: list,
    run_id: str,
    parser_version: str,
) -> tuple[int, int]:
    """LLM 풀로 issues_by_key를 병렬 파싱하고 DB에 직접 적재.

    Args:
        issues_by_key: {key: sections}
        llm_pools: ChatOpenAI 인스턴스 리스트
        run_id: parse 실행 ID (재개 시 같은 값으로 재호출)
        parser_version: parser 버전 문자열

    Returns:
        (success_count, failed_count). 셧다운 임계값 도달 시 sys.exit(2).
    """
    counter = FailureCounter(threshold=SHUTDOWN_THRESHOLD)
    success_count = 0
    failed_count = 0

    def call_llm(idx, key, sections):
        llm = llm_pools[idx % len(llm_pools)]
        prompt = PARSING_TEMPLATE.invoke({
            "section_description": sections["description"] or "없음",
            "section_checklist": sections["checklist"] or "없음",
            "section_outputs": sections["outputs"] or "없음",
        })
        resp = safe_structured_invoke(llm, prompt, SillogData)
        return key, resp

    # placeholder INSERT는 동시성 이슈 피하기 위해 메인 스레드에서 일괄 처리
    placeholders: dict[str, int] = {}
    with db.cursor() as cur:
        for key in issues_by_key.keys():
            placeholders[key] = insert_parsed_placeholder(
                cur, run_id=run_id, source_issue_key=key, parser_version=parser_version,
            )

    with ThreadPoolExecutor(max_workers=len(llm_pools)) as executor:
        futures = {
            executor.submit(call_llm, idx, key, sections): key
            for idx, (key, sections) in enumerate(issues_by_key.items())
        }

        for future in as_completed(futures):
            key = futures[future]
            parsed_id = placeholders[key]

            try:
                _, resp = future.result()
            except Exception as e:
                reason = f"exception: {e}"
                mark_parsed_failed(parsed_id, reason)
                failed_count += 1
                print(f"  [{key}] 예외 - {e}")
                if counter.bump_failure(reason) >= SHUTDOWN_THRESHOLD:
                    counter.exit("parse_description")
                continue

            if resp is None:
                reason = "safe_structured_invoke retry 끝까지 실패"
                mark_parsed_failed(parsed_id, reason)
                failed_count += 1
                print(f"  [{key}] LLM 실패 - 건너뜀")
                if counter.bump_failure(reason) >= SHUTDOWN_THRESHOLD:
                    counter.exit("parse_description")
                continue

            try:
                with db.cursor() as cur:
                    populate_parsed(cur, parsed_id, resp)
                success_count += 1
                counter.reset()
            except Exception as e:
                reason = f"populate_parsed 실패: {e}"
                mark_parsed_failed(parsed_id, reason)
                failed_count += 1
                print(f"  [{key}] DB 적재 실패 - {e}")
                if counter.bump_failure(reason) >= SHUTDOWN_THRESHOLD:
                    counter.exit("parse_description")

    print(f"파싱 결과: 성공 {success_count}건 / 실패 {failed_count}건")
    return success_count, failed_count
