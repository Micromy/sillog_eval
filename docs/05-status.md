# 05. 현재 상태 / TODO

기준일: 2026-05-06. 권위 있는 진행 SOT는 루트 `REFACTORING.md`. 이 문서는 사람이 읽기 좋은 요약 + 운영상 미연동 항목.

## 코드 베이스 상태

- 형태: **standalone Python 패키지** (`python -m sillog_eval.<module>`로 실행, Airflow 안팎 모두 가능)
- 이전 형태(Airflow DAG)는 원격 `https://github.com/Micromy/sillog_eval`에 보존
- 현 로컬 git: `~/Projects/sillog_eval` (2026-05-06 재초기화, 원격 미연동)

## 리팩토링 진행

| 항목 | 상태 |
|------|------|
| 1-1. `db.fetch_one`/`fetch_all` → `db.fetch`/`db.select` 호출부 정리 | ✅ |
| 1-2. `task_excution_method` → `task_execution_method` 오타 정정 | ✅ |
| 2-1. 문자열 유틸 → `common/text.py` 추출 (`truncate`, `clob_or_none`, `safe_dict`, `safe_list`) | ✅ |
| 2-2. `extractor.py` dict/Pydantic 중복 제거 | ✅ |
| 3-1. `score_async.py` 저장 함수 → `scorer/storage.py` 이전 | ✅ |
| 3-2. 패키지화 + entry 함수 `run()` 통일 (`python -m` 실행) | ✅ |
| 3-3. `common/convert.py`(`to_raw_dict` 등) 추출 검토 | ⬜ |
| 4-1. `llm.py`의 `from .config import *` wildcard 제거 | ⬜ |
| 4-2. 타입 힌트 보강 (`jira.py`, `storage.py`, `main.py`) | ⬜ |
| 4-3. `parsing_llm.py` 에러 핸들링 (silent skip → 수집/리포트) | ⬜ |

## 미연동 / 운영 갭

- **`.env`** 작성 필요 (커밋 금지). 최소: `PLATFORM`, `DTGPT_*` 또는 `DS_LLM_*`, `FILTER_ID`, `JIRA_*`, `ORACLE_*`, `SCORER_STORAGE_DIR`
- **프롬프트** (`EVALUATE_PROMPT`/`REFINE_PROMPT`/`REVIEW_PROMPT`/`PARSING_TEMPLATE`) — `config.py`에 placeholder만, 실제 템플릿은 로컬에서 채워야 함
- **DDL** — `eval_task_parsed*` / `eval_task_result*` / `sillog_tasks_attr` / `eval_task_rule_item` 스키마는 본 레포 외부. 운영 DB 적용 선결 필요
- **`STORAGE_DIR` 기본값**이 Windows 경로(`C:\Users\sh0913.park\...`)로 박혀 있음 — 리눅스에서 돌리려면 env override 필수
- **Jira `verify_ssl=False`** 하드코딩 — 환경 변경이 필요하면 코드 수정

## 다음 작업 추천

1. `.env` 템플릿(`.env.example`) 작성 + README 셋업 절 추가 (커밋용은 변수명만)
2. 4-1: `llm.py`의 wildcard import (`from .config import *`) 명시 import로 변경
3. 3-3: `to_raw_dict` 등 변환 헬퍼 → `common/convert.py` 추출
4. 4-2/4-3: 타입 힌트 + 에러 핸들링 보강
5. 통합 동작 테스트 (소량 이슈 1~2건으로 `python -m sillog_eval.main` 라운드트립)
