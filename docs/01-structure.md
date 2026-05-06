# 01. 구조 (Structure)

**원칙**: `{dag}/{task_id}.py`는 **task entry only** (argparse + 헬퍼 호출). 비즈니스 로직은 모두 `common/` 안의 인터페이스로 존재.

## 디렉토리 레이아웃

```
sillog_eval/                        # repo root (NOT a Python package)
├── run_task.py                     # CLI 진입점
├── REFACTORING.md
├── README.md
├── .gitignore
├── docs/
│
├── common/                         # 모든 헬퍼·인터페이스
│   ├── __init__.py
│   ├── config.py                   # env, 프롬프트, defaults
│   ├── llm.py                      # ChatOpenAI 팩토리 + safe_structured_invoke
│   ├── storage.py                  # pkl/json
│   ├── text.py                     # truncate / clob_or_none / safe_dict / safe_list
│   ├── convert.py                  # to_raw_dict (Pydantic | dict → dict)
│   │
│   ├── db/                         # DB 헬퍼 (Oracle + 도메인 적재/삭제)
│   │   ├── __init__.py             # cursor/select/fetch/execute/execute_many re-export
│   │   ├── cursor.py               # Oracle low-level (cursor 컨텍스트, select/fetch/execute)
│   │   ├── parsed.py               # SillogData → eval_task_parsed* + 일괄 upload()
│   │   ├── result.py               # IssueScore → eval_task_result* + migrate()
│   │   ├── reset.py                # eval_task_result* 자식→부모 삭제
│   │   └── meta.py                 # _meta.json 포맷 백필 (legacy → summary)
│   │
│   ├── jira/                       # Jira 도메인 헬퍼
│   │   ├── __init__.py
│   │   ├── client.py               # Jira REST + HTML 섹션 분리
│   │   ├── models.py               # SillogData Pydantic
│   │   └── llm_parser.py           # parse_issues_parallel (병렬 LLM 호출)
│   │
│   └── scoring/                    # 평가 엔진
│       ├── __init__.py             # 패키지 re-export
│       ├── base.py                 # ChecklistResult / IssueScore + 체크리스트
│       ├── extractor.py            # SillogData → 평탄화 텍스트
│       ├── agents.py               # CriteriaRefiner / SupervisorAgent
│       ├── scorer.py               # score_issues_batch / score_issue / build_summary
│       ├── storage.py              # 평가 결과 파일 I/O
│       └── evaluators/
│           ├── __init__.py
│           └── quantitative.py     # 룰 기반 정량 평가
│
├── parse/                          # 파싱 task entry only
│   ├── __init__.py
│   ├── fetch_jira.py               # task: Jira → jira_issues.pkl
│   └── parse_description.py        # task: pkl → LLM → parsed/{key}.json
│
├── score/                          # 평가 task entry only
│   ├── __init__.py
│   └── score_issues.py             # task: parsed/*.json → 평가
│
└── save/                           # DB저장 task entry only
    ├── __init__.py
    ├── upload_parsed.py            # task: parsed → DB
    ├── upload_results.py           # task: 평가 결과 → DB
    ├── migrate_meta.py             # task: _meta.json 백필
    └── reset_results.py            # task: 결과 테이블 삭제
```

**도메인 디렉토리(`parse/`, `score/`, `save/`)에는 task entry만 존재.** 모든 비즈니스 로직은 `common/`의 sub-package에 위치.

## Task 인벤토리 (변동 없음)

| 호출 | 모듈 | 핵심 헬퍼 |
|------|------|-----------|
| `parse fetch_jira` | `parse/fetch_jira.py` | `common.jira.client.{get_jql_filter, get_sections_by_key}` |
| `parse parse_description` | `parse/parse_description.py` | `common.jira.llm_parser.parse_issues_parallel` |
| `score score_issues` | `score/score_issues.py` | `common.scoring.scorer.score_issues_batch` |
| `save upload_parsed` | `save/upload_parsed.py` | `common.db.parsed.upload` |
| `save upload_results` | `save/upload_results.py` | `common.db.result.migrate` |
| `save migrate_meta` | `save/migrate_meta.py` | `common.db.meta.migrate_all` |
| `save reset_results` | `save/reset_results.py` | `common.db.reset.reset` |

## Task 파일 컨벤션

각 task 파일은 다음 패턴을 따름:

```python
# {dag}/{task_id}.py
import argparse
from common.<sub>.<helper> import <함수>

def run() -> None:
    parser = argparse.ArgumentParser(...)
    parser.add_argument(...)
    args = parser.parse_args()
    <함수>(...)

if __name__ == "__main__":
    run()
```

- task 파일에는 비즈니스 로직 없음, argparse + 헬퍼 호출만
- 헬퍼는 `common/` 안의 적절한 sub-package에 위치
- `run()`은 무인자 (run_task.py 디스패처가 sys.argv 보정으로 표준 argparse 가능하게 해줌)

## 외부 의존
- `langchain_openai` / `langchain_core` — LLM
- `atlassian-python-api` + `beautifulsoup4` — Jira
- `oracledb` (thin) + `python-dotenv` — DB / env
- `pydantic` — 모델
