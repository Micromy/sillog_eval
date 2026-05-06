from .config import (
    PLATFORM,
    DTGPT_MODEL,
    DS_LLM_MODEL,
    FILTER_ID,
    LLM_POOL_SIZE,
    STORAGE_DIR,
)
from .jira import get_jql_filter, get_sections_by_key
from .storage import save_pkl, load_pkl
from .llm import create_llm
from .parsing_llm import parse_issues_parallel
from .score_async import score_issues_batch


def run() -> list:
    model_name: str = DTGPT_MODEL if PLATFORM == 'DTGPT' else DS_LLM_MODEL if PLATFORM == 'DS_LLM' else ""

    sections_file_path = STORAGE_DIR / "jira_issues.pkl"
    if sections_file_path.exists():
        issues_by_key = load_pkl(sections_file_path)
    else:
        jql = get_jql_filter(FILTER_ID)
        issues_by_key = get_sections_by_key(jql)
        save_pkl(sections_file_path, issues_by_key)

    llm_pools = [create_llm() for _ in range(LLM_POOL_SIZE)]

    parsed_issues = {}
    remaining = issues_by_key

    for attempt in range(3):
        if not remaining:
            break
        new_parsed, failed_keys = parse_issues_parallel(
            issues_by_key=remaining,
            llm_pools=llm_pools
        )
        parsed_issues.update(new_parsed)
        remaining = {k: issues_by_key[k] for k in failed_keys}

    failed_keys = list(remaining.keys())
    print(f"최종 실패: {len(failed_keys)}건 - {failed_keys}")

    results = score_issues_batch(
        items=[(key, data) for key, data in parsed_issues.items()],
        llm_pool=llm_pools,
        model_name=model_name
    )

    return results


if __name__ == "__main__":
    run()
