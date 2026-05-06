# 01. 구조 (Structure)

## 디렉토리 레이아웃

```
sillog_eval/                       # repo root (NOT a Python package)
├── run_task.py                    # CLI 진입점 (모든 task의 단일 dispatcher)
├── REFACTORING.md                 # 리팩토링 진행 SOT
├── README.md
├── .gitignore
├── docs/
│
├── common/                        # 공유 헬퍼 (task 아님)
│   ├── __init__.py
│   ├── config.py                  # 전역 설정 (env 로드, 프롬프트, 타임아웃)
│   ├── db.py                      # Oracle cursor/select/fetch/execute
│   ├── llm.py                     # ChatOpenAI 팩토리 + safe_structured_invoke
│   ├── storage.py                 # 범용 파일 I/O (pkl, json)
│   ├── text.py                    # truncate, clob_or_none, safe_dict, safe_list
│   └── convert.py                 # to_raw_dict (Pydantic | dict → dict)
│
├── parse/                         # 파싱 도메인
│   ├── __init__.py
│   ├── fetch_jira.py              # task: Jira fetch + 섹션 분리 → jira_issues.pkl
│   ├── parse_description.py       # task: pkl → LLM 파싱 → parsed/{key}.json
│   ├── jira.py                    # 헬퍼: Jira REST + BeautifulSoup
│   ├── llm_parser.py              # 헬퍼: parse_issues_parallel (병렬 LLM 호출)
│   ├── models.py                  # 헬퍼: SillogData 계열 Pydantic
│   └── persistence.py             # 헬퍼: SillogData → eval_task_parsed* 적재
│
├── score/                         # 평가 도메인
│   ├── __init__.py                # 패키지 re-export (ChecklistResult 등)
│   ├── score_issues.py            # task: parsed/*.json → 일괄 평가
│   ├── scorer.py                  # 헬퍼: score_issues_batch / score_issue / build_summary
│   ├── base.py                    # ChecklistResult / IssueScore / 정량·정성 체크리스트
│   ├── extractor.py               # SillogData → 평탄화 텍스트 (LLM 입력용)
│   ├── agents.py                  # CriteriaRefiner / SupervisorAgent
│   ├── storage.py                 # 평가 결과 파일 I/O (save_item/save_meta 등)
│   └── evaluators/
│       ├── __init__.py
│       └── quantitative.py        # 룰 기반 정량 평가 (LLM 무사용)
│
└── save/                          # DB저장 도메인
    ├── __init__.py
    ├── upload_parsed.py           # task: parsed/*.json → eval_task_parsed*
    ├── upload_results.py          # task: 평가 결과 → eval_task_result*
    ├── migrate_meta.py            # task: _meta.json 포맷 백필
    └── reset_results.py           # task: eval_task_result* 삭제 (dry-run 기본)
```

**루트는 패키지가 아니다** (`__init__.py` 없음). repo 루트가 CWD가 되어 `common`, `parse`, `score`, `save`가 top-level package로 import 됨. 이전 Airflow 패턴 그대로.

## Task 인벤토리

7개 task. 모두 무인자 `def run()` export.

| 호출 | 설명 |
|------|------|
| `python run_task.py parse fetch_jira` | Jira fetch + 캐시 |
| `python run_task.py parse parse_description` | LLM 파싱 (재시도 3회) |
| `python run_task.py score score_issues` | 일괄 평가 |
| `python run_task.py save upload_parsed` | parsed JSON → DB |
| `python run_task.py save upload_results` | 평가 결과 → DB |
| `python run_task.py save migrate_meta` | `_meta.json` 백필 |
| `python run_task.py save reset_results` | 결과 테이블 삭제 |

CLI 인자가 있는 task(save 도메인)는 dispatcher가 sys.argv를 task 기준으로 보정해서 표준 argparse 그대로 동작.

## 계층 책임

### `run_task.py`
- `<dag>.<task_id>` 형태 동적 import → `module.run()` 호출
- 호출 전 `sys.argv = [module_path] + sys.argv[3:]`로 보정 (task가 표준 argparse 사용 가능)
- `run()` 미정의 모듈은 에러로 종료

### `common/` (공유 헬퍼)
| 모듈 | 책임 |
|------|------|
| `config.py` | `.env` 로드, PLATFORM 분기, 프롬프트, 타임아웃·동시성 defaults |
| `llm.py` | DTGPT/DS_LLM 분기로 ChatOpenAI 인스턴스 생성, `safe_structured_invoke` (structured → 수동 JSON → retry → None) |
| `db.py` | Oracle thin client, `cursor()` 컨텍스트 (commit/rollback 자동), `select`/`fetch`/`execute`/`execute_many` |
| `storage.py` | pkl/json I/O (단순) |
| `text.py` | VARCHAR2 byte-safe truncate, CLOB 변환, dict/list 안전 변환 |
| `convert.py` | SillogData(Pydantic) | dict → dict 정규화 |

### `parse/` (파싱 도메인)
- **task**: `fetch_jira` (Jira→pkl), `parse_description` (pkl→LLM→json)
- **헬퍼**: `jira.py` (Jira REST + 섹션 분리), `models.py` (SillogData), `llm_parser.py` (병렬 LLM 호출), `persistence.py` (DB 적재)

### `score/` (평가 도메인)
- **task**: `score_issues` (parsed→평가→파일 저장)
- **헬퍼**: `scorer.py` (orchestration: score_issue 라운드 루프, batch), `base.py` (체크리스트/dataclass), `extractor.py` (평탄화), `agents.py` (CriteriaRefiner/SupervisorAgent), `evaluators/quantitative.py` (룰 기반), `storage.py` (평가 결과 파일 I/O)

### `save/` (DB저장 도메인)
- **task**: `upload_parsed`, `upload_results`, `migrate_meta`, `reset_results`
- 각 task는 자체 argparse로 CLI 인자 처리. 헬퍼는 task 파일 내부에 함께 (migration 로직이 task 단위로 응집되어 있어 분리하지 않음)

## 외부 의존
- `langchain_openai` / `langchain_core` — LLM 호출 + structured output
- `atlassian-python-api` + `beautifulsoup4` — Jira / HTML
- `oracledb` (thin mode) + `python-dotenv` — DB / env
- `pydantic` — 모델
