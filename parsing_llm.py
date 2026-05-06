from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import json

from .config import STORAGE_DIR, PARSING_TEMPLATE
from .llm import safe_structured_invoke
from .models import SillogData
from .storage import save_json


def parse_issues_parallel(issues_by_key, llm_pools, output_dir="parsed"):
    """
    LLM 풀을 활용해 issues_by_key를 병렬로 파싱한다.

    Args:
        issues_by_key (dict): {key: sections} 형태의 입력 데이터
        llm_pools (list): ChatOpenAI 인스턴스 리스트
        output_dir (str): 파싱 결과 JSON 저장 디렉토리

    Returns:
        tuple: (parsed_issues: dict, failed_keys: list)
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

    parsed_issues = {}
    storage_path = STORAGE_DIR / output_dir
    os.makedirs(STORAGE_DIR / output_dir, exist_ok=True)

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
                print(f"  [{key}] 예외 발생 - {e}")
                continue

            if resp is None:
                print(f"  [{key}] 파싱 실패 - 건너뜀")
                continue

            parsed_issues[key] = resp.model_dump()
            save_json(storage_path / f"{key}.json", parsed_issues[key])

    failed_keys = [key for key in issues_by_key.keys() if key not in parsed_issues]
    print(f"실패: {len(failed_keys)}건 - {failed_keys}")

    return parsed_issues, failed_keys
