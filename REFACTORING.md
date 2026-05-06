# sillog_eval 코드 정리 기록

코드 리팩토링 진행 상황을 기록한 문서.
정리 완료 후 이 파일은 삭제하거나 docs/로 이동.

---

## 현재 프로젝트 구조

(상세는 `docs/01-structure.md`)

```
sillog_eval/                       # repo root, NOT a Python package
├── run_task.py                    # CLI dispatcher
├── REFACTORING.md / README.md / docs/ / .gitignore
│
├── common/                        # 모든 헬퍼·인터페이스
│   ├── config / llm / storage / text / convert (top-level)
│   ├── db/                        # cursor, parsed, result, reset, meta
│   ├── jira/                      # client, models, llm_parser
│   └── scoring/                   # base, extractor, agents, scorer, storage, evaluators/
│
├── parse/                         # task entry only
│   ├── fetch_jira.py
│   └── parse_description.py
├── score/                         # task entry only
│   └── score_issues.py
└── save/                          # task entry only
    ├── upload_parsed.py
    ├── upload_results.py
    ├── migrate_meta.py
    └── reset_results.py
```

---

## 정리 계획

### 1. 버그/불일치 수정 ✅ 완료

#### 1-1. db.py API 불일치 ✅

`persistence.py`와 `reset_eval_results.py`에서 `db.fetch_one()`, `db.fetch_all()`로 호출하고 있었으나,
`db.py`에는 `fetch()`, `select()`로 정의되어 있었음.

**결정:** `select`/`fetch`로 통일 (db.py 유지, 호출부 수정)

**변경 파일:**
- `parser/persistence.py` — `fetch_one` → `fetch`, `fetch_all` → `select` (4곳)
- `reset_eval_results.py` — `fetch_one` → `fetch`, `fetch_all` → `select` (4곳)

```
fix: db.py API 호출 불일치 수정 (fetch_one→fetch, fetch_all→select)
```

#### 1-2. task_excution_method 오타 ✅

`excution` → `execution` 오타 수정. DB 컬럼은 이미 `task_execution_method`로 올바름.

**결정:** 필드명 수정만 (기존 JSON은 재파싱)

**변경 파일:**
- `models.py` — `Description.task_excution_method` → `task_execution_method`
- `scorer/extractor.py` — dict/Pydantic 양쪽 접근자 수정 (2곳)
- `parser/persistence.py` — dict 접근자 수정 (1곳)

```
fix: task_excution_method 오타 수정 → task_execution_method
```

---

### 2. 중복 제거 ✅ 완료

#### 2-1. 공통 유틸 함수 추출 ✅

`_truncate`, `_clob_or_none`, `_safe_dict`, `_safe_list`가 `persistence.py`와 `migrate_eval_results.py`에 중복.

**결정:** `common/text.py`로 추출, 접두어 `_` 제거

**변경 파일:**
- `common/text.py` — 신규 (truncate, clob_or_none, safe_dict, safe_list)
- `parser/persistence.py` — 로컬 함수 4개 삭제, common.text import
- `migrate_eval_results.py` — 로컬 _truncate 삭제, common.text import

```
refactor: 공통 문자열 유틸을 common/text.py로 추출
```

#### 2-2. extractor.py dict/Pydantic 중복 제거 ✅

dict 처리 ~80줄과 Pydantic 처리 ~60줄이 거의 동일한 로직이었음.
입구에서 dict로 통일(`model_dump()`/`dict()`) 후 Pydantic 분기 전체 삭제.

**변경 파일:**
- `scorer/extractor.py` — 184줄 → 113줄 (-70줄). dict 분기 단일 경로.

**부수 효과:**
- `description=None`인 Pydantic 입력 시 이전엔 AttributeError 크래시 → 빈 결과 반환으로 강건성 향상
- 잘못된 타입 입력 시 명시적 `TypeError` 발생

```
refactor: extractor.py dict/Pydantic 분기 통합
```

---

### 3. 모듈 구조 개선 ✅ 완료

#### 3-1. storage.py 역할 정리 ✅

루트 `storage.py`(pkl/json 3줄)는 범용 파일 I/O로 유지.
`score_async.py` 내 저장 함수들(`save_item_result`, `save_meta`, `save_iteration`, `load_previous_results` + 경로 헬퍼 `_final_dir`/`_items_dir`/`_iteration_dir`)을 `scorer/storage.py`로 분리.

**변경 파일:**
- `scorer/storage.py` — 신규 (151줄, 4개 public + 3개 private 헬퍼)
- `score_async.py` — 130줄 삭제 (저장 함수 정의 제거), 6줄 import 추가, `from pathlib import Path` 미사용으로 제거 (723줄 → 593줄)

```
refactor: 평가 결과 저장 헬퍼를 scorer/storage.py로 분리
```

#### 3-2. 패키지화 + entry 통일 ✅

스크립트 레벨 코드를 함수로 감싸는 작업과 함께, 패키지 내부 import를 모두 상대 import로 전환하여 `python -m sillog_eval.<module>` 식으로 실행 가능하게 함. 이전 Airflow 체계와의 일관성을 위해 entry 함수명은 무인자 `run()`으로 통일.

**변경 내용:**
- 모든 패키지 내부 import → 상대 import (`from .config`, `from ..common.db` 등)
- 5개 entry 스크립트의 entry 함수를 무인자 `def run()`으로 통일:
  - `main.py`: `def run()` (스크립트 레벨 코드 감쌈)
  - `upload_parsed.py`: 기존 `run(...)` → `upload(...)`, 기존 `main()` → `run()`
  - `migrate_eval_results.py`: 기존 `run(...)` → `migrate(...)`, CLI 블록을 `def run()`으로 감쌈
  - `migrate_meta.py`: `def main()` → `def run()`
  - `reset_eval_results.py`: 기존 `run(...)` → `reset(...)`, CLI 블록을 `def run()`으로 감쌈
- 모든 entry 스크립트 끝에 `if __name__ == "__main__": run()`

**변경 파일 (10개):**
- `main.py`, `llm.py`, `parsing_llm.py`, `score_async.py` — import 상대화 + entry
- `upload_parsed.py`, `migrate_eval_results.py`, `migrate_meta.py`, `reset_eval_results.py` — import 상대화 + entry rename
- `parser/persistence.py` — `from common` → `from ..common`
- `scorer/agents.py` — `from config` → `from ..config`

**실행 방법:**
- 패키지로: `cd ~/Projects && python -m sillog_eval.main`, `python -m sillog_eval.upload_parsed --help` 등
- Airflow에서: BashOperator로 `python -m sillog_eval.<module>` 호출 (env 변수로 .env 대체)

```
refactor: 패키지화 + entry 함수 run() 통일 (python -m 실행 지원)
```

#### 3-3. common/ 추가 확장 ✅

`to_raw_dict`(SillogData Pydantic | dict → dict)이 3곳에 중복되어 있던 것을 `common/convert.py`로 추출.

**이전 중복 위치:**
- `score_async.py:69-77` — `def to_raw_dict()` (canonical)
- `scorer/extractor.py` — `extract()` 입구 inline
- `parser/persistence.py` — `save_parsed()` 입구 inline (필드 검증 분기 순서가 약간 달랐음)

**변경 파일:**
- `common/convert.py` — 신규 (단일 정의)
- `score_async.py` — local def 삭제, `from .common.convert import to_raw_dict`
- `scorer/extractor.py` — inline 분기 삭제, `from ..common.convert import to_raw_dict` 후 한 줄로
- `parser/persistence.py` — inline 분기 삭제, 같은 import + 한 줄

```
refactor: to_raw_dict를 common/convert.py로 추출
```

---

### 4. 코드 품질 ✅ 완료

#### 4-1. wildcard import 제거 ✅

`from .config import *`이 `llm.py`/`main.py` 두 곳에 있었음. 실제 사용 이름만 명시 import로 교체.

**변경 파일:**
- `llm.py` — `PLATFORM`, `DTGPT_URL/MODEL/TOKEN`, `DS_LLM_URL/MODEL/HEADER` 명시
- `main.py` — `PLATFORM`, `DTGPT_MODEL`, `DS_LLM_MODEL`, `FILTER_ID`, `LLM_POOL_SIZE`, `STORAGE_DIR` 명시

```
refactor: wildcard import 제거 (llm.py, main.py)
```

#### 4-2. 타입 힌트 보강 ✅

`jira.py`, `storage.py`, `main.py`에 함수 시그니처 타입 힌트 추가.

**변경 파일:**
- `jira.py` — 4개 함수 모두 인자/반환 타입 (`get_all_issues -> list[dict]`, `get_jql_filter(filter_id: str) -> str`, `split_jira_sections(description_html: str) -> dict[str, str]`, `get_sections_by_key -> dict[str, dict[str, str]]`)
- `storage.py` — `save_pkl(path: Path, data: Any) -> None`, `load_pkl(path: Path) -> Any`, `save_json(path: Path, data: Any) -> None`. 미사용 `output = ""` 변수 제거.
- `main.py` — `def run() -> list`, `model_name: str` 명시

```
refactor: jira.py / storage.py / main.py 타입 힌트 보강
```

#### 4-3. 에러 핸들링 패턴 통일 ✅

`parsing_llm.py`의 silent skip(콘솔 print만)을 카테고리별 에러 수집 + 파일 리포트로 전환.

**변경 내용:**
- 실패 케이스를 두 카테고리로 분류:
  - `exception` — future.result() 예외
  - `parse_failed` — `safe_structured_invoke`가 None 반환
- 실행 끝에 카테고리별 카운트 요약 (`성공 N건 / 실패 M건 (exception=X, parse_failed=Y)`)
- 실패 1건 이상이면 `{STORAGE_DIR}/{output_dir}/_parse_errors_<ts>.json`에 구조화된 로그 저장 (`upload_parsed.py`의 `_load_errors_*.json` 패턴과 동일)
- 함수 시그니처 타입 힌트 추가 (4-2 후속)
- 호출자(main.py) 인터페이스(2-tuple) 유지

```
refactor: parsing_llm.py 에러 수집/리포트 패턴 적용
```

---

### R. 디렉토리 재편성 (task-dispatch 구조) ✅

이전 Airflow `run_task.py` 패턴으로 전면 재편성. 루트가 더 이상 패키지 아님.

**변경:**
- 루트 `__init__.py` 삭제, `main.py` 삭제 (run_task.py + 3개 task로 분할)
- 디렉토리 이름 변경: `parser/` → `parse/`, `scorer/` → `score/`
- 신규 디렉토리: `save/` (DB저장 도메인)
- 헬퍼 파일 이동:
  - `config.py`, `llm.py`, `storage.py` → `common/`
  - `jira.py`, `models.py`, `parsing_llm.py`(→`llm_parser.py`), `parser/persistence.py` → `parse/`
  - `score_async.py`(→`scorer.py`), `scorer/*` → `score/`
  - `upload_parsed.py`, `migrate_eval_results.py`(→`upload_results.py`), `migrate_meta.py`, `reset_eval_results.py`(→`reset_results.py`) → `save/`
- 신규 task entry 3개: `parse/fetch_jira.py`, `parse/parse_description.py`, `score/score_issues.py`
- 모든 상대 import → 절대 import (`from common.config import ...` 등). 같은 패키지 내 sibling은 `from .X` 유지.
- `run_task.py`에 `sys.argv` 보정 로직 추가 → task가 표준 argparse 사용 가능

**Task 인벤토리:**
| 호출 | 모듈 | 비고 |
|------|------|------|
| `parse fetch_jira` | `parse/fetch_jira.py` | Jira → pkl, 캐시 idempotent |
| `parse parse_description` | `parse/parse_description.py` | pkl → LLM → json (재시도 3회) |
| `score score_issues` | `score/score_issues.py` | parsed → 평가 |
| `save upload_parsed` | `save/upload_parsed.py` | parsed → DB |
| `save upload_results` | `save/upload_results.py` | 평가 결과 → DB |
| `save migrate_meta` | `save/migrate_meta.py` | `_meta.json` 백필 |
| `save reset_results` | `save/reset_results.py` | 결과 테이블 삭제 |

```
refactor: task-dispatch 구조로 재편성 (run_task.py + 3개 도메인)
```

---

### R-2. task entry / common 인터페이스 분리 ✅

`{dag}/{task_id}.py`에는 task 진입(argparse + 헬퍼 호출)만 두고, 비즈니스 로직은 모두 `common/` 안의 sub-package로 이전. 도메인 디렉토리는 thin wrapper로 환원.

**`common/` 재구성:**
- `common/db/` 패키지화 (기존 `common/db.py` → `common/db/cursor.py`로 승격, `__init__.py`에서 re-export)
- `common/jira/` 신규: `client.py`(JIRA REST), `models.py`(SillogData), `llm_parser.py`(병렬 파싱)
- `common/scoring/` 신규: `base/extractor/agents/scorer/storage` + `evaluators/`
- `common/db/parsed.py` — SillogData → DB 적재 + 일괄 `upload()` 함수
- `common/db/result.py` — IssueScore → DB 마이그레이션 (8개 헬퍼 + `migrate()`)
- `common/db/reset.py` — eval_task_result* 삭제 헬퍼 + `reset()`
- `common/db/meta.py` — `_meta.json` 백필 + `migrate_all()`

**`save/` 슬림화:**
| 파일 | 이전 | 이후 |
|------|------|------|
| `save/upload_parsed.py` | 200줄 | 45줄 |
| `save/upload_results.py` | 500줄 | 40줄 |
| `save/migrate_meta.py` | 310줄 | 28줄 |
| `save/reset_results.py` | 270줄 | 32줄 |

**`parse/`, `score/` 슬림화:**
- `parse/jira.py`, `parse/models.py`, `parse/llm_parser.py`, `parse/persistence.py` → `common/jira/`, `common/db/parsed.py`로 이전
- `score/base.py`, `score/extractor.py`, `score/agents.py`, `score/scorer.py`, `score/storage.py`, `score/evaluators/` → `common/scoring/`으로 이전
- 각 도메인 디렉토리에는 task entry만 남음

```
refactor: task entry / common 인터페이스 분리 (헬퍼 모두 common/으로)
```

---

## 정리 규칙

- 코드 변경 시 커밋 메시지 함께 기록
- 기존 동작은 유지 (리팩토링 only, 기능 변경 없음)
- config.py 민감정보는 문서에 포함하지 않음
