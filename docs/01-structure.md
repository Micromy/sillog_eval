# 01. 구조 (Structure)

## 디렉토리 레이아웃

```
sillog_eval/
├── __init__.py                # 빈 패키지 마커
├── config.py                  # 전역 설정 (env 로드, 프롬프트, 타임아웃)
├── REFACTORING.md             # 리팩토링 진행 SOT
│
├── main.py                    # end-to-end 진입점 (Jira → 파싱 → 평가)
│
├── jira.py                    # Jira REST 호출 + HTML 섹션 분리
├── llm.py                     # LLM 클라이언트 팩토리 + safe_structured_invoke
├── models.py                  # Pydantic 모델 (SillogData 계열)
├── parsing_llm.py             # 병렬 파싱 (issues → SillogData)
├── storage.py                 # 범용 파일 I/O (pkl, json)
│
├── score_async.py             # 평가 엔진 (정량 + 정성 + 감독관, 항목별 저장)
│
├── upload_parsed.py           # 로컬 parsed JSON → eval_task_parsed 적재
├── migrate_eval_results.py    # 로컬 평가결과 → eval_task_result 마이그레이션
├── migrate_meta.py            # _meta.json 포맷 마이그레이션 (summary 필드 추가)
├── reset_eval_results.py      # eval_task_result 계열 리셋 (dry-run 기본)
│
├── common/
│   ├── db.py                  # Oracle 연결/쿼리 헬퍼 (cursor/select/fetch/execute)
│   └── text.py                # 문자열 유틸 (truncate/clob_or_none/safe_dict/safe_list)
│
├── parser/
│   └── persistence.py         # eval_task_parsed 계열 5개 테이블 적재
│
└── scorer/
    ├── __init__.py            # 패키지 re-export
    ├── base.py                # ChecklistResult/IssueScore + 정량·정성 체크리스트
    ├── extractor.py           # SillogData → 평탄화 텍스트 (LLM 입력용)
    ├── agents.py              # CriteriaRefiner / SupervisorAgent
    └── evaluators/
        └── quantitative.py    # 룰 기반 정량 평가 (LLM 무사용)
```

## 계층 책임

### 진입 (`main.py`)
- `config.py` 전역 설정 → Jira fetch → 파싱 → 평가 순서를 스크립트 레벨로 호출
- 현재 함수화되어 있지 않음 (REFACTORING 3-2 예정)

### 외부 연동
| 모듈 | 책임 |
|------|------|
| `jira.py` | atlassian-python-api로 JQL 조회 + `<div class="jefolding">` 단위 description/checklist/outputs 섹션 분리 |
| `llm.py` | DTGPT / DS_LLM 두 플랫폼 분기로 `ChatOpenAI` 인스턴스 생성, `safe_structured_invoke`(structured → 수동 JSON → retry → None) |

### 데이터 모델 (`models.py`)
- `SillogData`(루트) ⊃ `Description` + `checklist:list[str]` + `outputs:list[Output]`
- `Description` ⊃ `purpose` + `input_data:list[InputData]` + `task_manager:Manager` + `task_execution_method` + `tool`
- `InputData`/`Output` ⊃ `file_name`/`file_format`/`file_path` + `managers`(`receivers`)
- `Manager` ⊃ `role` + `role_type` + `job_category`
- 모든 노드에 `make_fill_nulls()` validator: None/"" → 타입에 맞는 빈 값으로 보정 (list→[], 중첩모델→None, str→"")
- `checklist`는 str/dict 모두 받아서 list[str]로 정규화

### 파싱
- `parsing_llm.parse_issues_parallel(issues_by_key, llm_pools)`
- ThreadPool로 LLM 풀 라운드로빈, 항목별 `{key}.json`을 `STORAGE_DIR/parsed/`에 저장
- 실패 키만 추려 호출자(main)에서 최대 3회 재시도

### 평가 (`score_async.py` + `scorer/`)
- 단건: `score_issue(key, sillog_data, llm_pool, model_name, ...)`
- 일괄: `score_issues_batch(items, llm_pool, model_name, ...)` — `ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS)`
- 단계:
  1. **정량** (`QuantitativeEvaluator`, 룰 기반, LLM 무사용)
  2. **정성** (라운드 루프, `evaluate_qualitative_batch`, LLM 풀 병렬)
  3. **감독관** (`SupervisorAgent.review`, retry wrapper)
  4. 미승인 시 `CriteriaRefiner`로 다음 라운드 기준 고도화
  5. 최종 점수 + 총평 → 항목별 + 메타 + 라운드 스냅샷 파일 저장

### 저장 / 영속화
| 레이어 | 모듈 | 매핑 대상 |
|--------|------|-----------|
| 평가 결과 (파일) | `score_async.save_item_result` / `save_meta` / `save_iteration` | `EVAL_TASK_RESULT_ITEM` / `EVAL_TASK_RESULT` / (디버깅) |
| 파싱 결과 (DB) | `parser.persistence.save_parsed` | `eval_task_parsed` + `_input` + `_output` + `_check` + `_manager` |
| 평가 결과 (DB 마이그레이션) | `migrate_eval_results.py` | `eval_task_result` 계열 |
| DB 헬퍼 | `common.db` | Oracle thin client, `cursor()` 컨텍스트 (commit/rollback 자동) |

### 운영 스크립트
- `upload_parsed.py` — 로컬 `parsed/*.json` 일괄 적재 (CLI, dry-run 지원)
- `migrate_eval_results.py` — 로컬 평가결과 디렉토리 → DB 일괄 적재
- `migrate_meta.py` — 기존 `_meta.json`에 `summary` 구조 필드 백필
- `reset_eval_results.py` — `eval_task_result` 계열 삭제 (기본 dry-run, `--execute` 명시 필요)

## 외부 의존
- `langchain_openai` / `langchain_core` — LLM 호출 + structured output
- `atlassian-python-api` + `beautifulsoup4` — Jira / HTML
- `oracledb` (thin mode) + `python-dotenv` — DB / env
- `pydantic` — 모델
