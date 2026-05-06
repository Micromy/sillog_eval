from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from datetime import datetime

from .config import STORAGE_DIR, PARSING_TEMPLATE
from .llm import safe_structured_invoke
from .models import SillogData
from .storage import save_json


def parse_issues_parallel(
    issues_by_key: dict[str, dict[str, str]],
    llm_pools: list,
    output_dir: str = "parsed",
) -> tuple[dict, list[str]]:
    """
    LLM 풀을 활용해 issues_by_key를 병렬로 파싱한다.

    실패는 카테고리별로 수집하여 콘솔에 요약하고, 1건 이상이면
    `{STORAGE_DIR}/{output_dir}/_parse_errors_<ts>.json`에 구조화된 로그를 남긴다.
    호출자는 (parsed, failed_keys) 2-tuple만 받는다 (재시도 루프용).

    Args:
        issues_by_key: {key: sections} 형태의 입력 데이터
        llm_pools: ChatOpenAI 인스턴스 리스트
        output_dir: 파싱 결과 JSON 저장 디렉토리 (STORAGE_DIR 하위)

    Returns:
        (parsed_issues: dict, failed_keys: list[str])
    """
    def process_one(idx, key, sections):
        llm = llm_pools[idx % len(llm_pools)]
        prompt = PARSING_TEMPLATE.invoke({
            "section_description": sections["description"] or "없음",
            "section_checklist": sections["checklist"] or "없음",
            "section_outputs": sections["outputs"] or "없음",
        })
        resp = safe_structured_invoke(llm, prompt, SillogData)
        return key, resp

    parsed_issues: dict = {}
    errors: list[dict] = []
    storage_path = STORAGE_DIR / output_dir
    os.makedirs(storage_path, exist_ok=True)

    with ThreadPoolExecutor(max_workers=len(llm_pools)) as executor:
        futures = {
            executor.submit(process_one, idx, key, sections): key
            for idx, (key, sections) in enumerate(issues_by_key.items())
        }

        for future in as_completed(futures):
            key = futures[future]
            try:
                key, resp = future.result()
            except Exception as e:
                errors.append({"key": key, "reason": "exception", "error": str(e)})
                print(f"  [{key}] 예외 발생 - {e}")
                continue

            if resp is None:
                errors.append({"key": key, "reason": "parse_failed", "error": "safe_structured_invoke 반환 None"})
                print(f"  [{key}] 파싱 실패 - 건너뜀")
                continue

            parsed_issues[key] = resp.model_dump()
            save_json(storage_path / f"{key}.json", parsed_issues[key])

    failed_keys = [key for key in issues_by_key.keys() if key not in parsed_issues]

    by_reason: dict[str, int] = {}
    for e in errors:
        by_reason[e["reason"]] = by_reason.get(e["reason"], 0) + 1
    summary = ", ".join(f"{reason}={count}" for reason, count in by_reason.items()) or "(없음)"
    print(f"파싱 결과: 성공 {len(parsed_issues)}건 / 실패 {len(failed_keys)}건 ({summary})")
    if failed_keys:
        print(f"  실패 키: {failed_keys}")

    if errors:
        error_log_path = storage_path / f"_parse_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        save_json(error_log_path, errors)
        print(f"  에러 로그 저장: {error_log_path}")

    return parsed_issues, failed_keys
