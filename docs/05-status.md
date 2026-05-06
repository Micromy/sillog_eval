# 05. 현재 상태 / TODO

기준일: 2026-05-06. 권위 있는 진행 SOT는 루트 `REFACTORING.md`. 이 문서는 사람이 읽기 좋은 요약 + 운영상 미연동 항목.

## 코드 베이스 상태

- 형태: **standalone Python 모듈** (Airflow 의존 제거)
- 이전 형태(Airflow DAG)는 원격 `https://github.com/Micromy/sillog_eval`에 보존
- 현 로컬 git: `~/Projects/sillog_eval` (2026-05-06 재초기화, 원격 미연동)
- 25개 파일, 약 3,745 LOC

## 리팩토링 진행

| 항목 | 상태 |
|------|------|
| 1-1. `db.fetch_one`/`fetch_all` → `db.fetch`/`db.select` 호출부 정리 | ✅ |
| 1-2. `task_excution_method` → `task_execution_method` 오타 정정 | ✅ |
| 2-1. 문자열 유틸 → `common/text.py` 추출 (`truncate`, `clob_or_none`, `safe_dict`, `safe_list`) | ✅ |
| 2-2. `extractor.py` dict/Pydantic 중복 제거 (`to_raw_dict` 단일 경로) | ⬜ |
| 3-1. `score_async.py` 저장 함수 → `scorer/storage.py` 이전 + 루트 `storage.py` 역할 정리 | ⬜ |
| 3-2. `main.py` 함수화 (`def main()` + `if __name__ == "__main__"`) | ⬜ |
| 3-3. `common/convert.py`(`to_raw_dict` 등) 추출 검토 | ⬜ |
| 4-1. `llm.py`의 `from config import *` 제거 | ⬜ |
| 4-2. 타입 힌트 보강 (`jira.py`, `storage.py`, `main.py`) | ⬜ |
| 4-3. `parsing_llm.py` 에러 핸들링 (silent skip → 수집/리포트) | ⬜ |

## 미연동 / 운영 갭

- **`.env`** 작성 필요 (커밋 금지). 최소: `PLATFORM`, `DTGPT_*` 또는 `DS_LLM_*`, `FILTER_ID`, `JIRA_*`, `ORACLE_*`, `SCORER_STORAGE_DIR`
- **프롬프트** (`EVALUATE_PROMPT`/`REFINE_PROMPT`/`REVIEW_PROMPT`/`PARSING_TEMPLATE`) — `config.py`에 placeholder만, 실제 템플릿은 로컬에서 채워야 함
- **DDL** — `eval_task_parsed*` / `eval_task_result*` / `sillog_tasks_attr` / `eval_task_rule_item` 스키마는 본 레포 외부. 운영 DB 적용 선결 필요
- **`STORAGE_DIR` 기본값**이 Windows 경로(`C:\Users\sh0913.park\...`)로 박혀 있음 — 리눅스에서 돌리려면 env override 필수
- **Jira `verify_ssl=False`** 하드코딩 — 환경 변경이 필요하면 코드 수정

## 다음 작업 추천

1. `.env` 템플릿 작성 + README의 셋업 절 추가 (커밋용은 변수명만)
2. `extractor.py` 중복 제거 (REFACTORING 2-2) — 가장 짧고 효과 큰 작업
3. `main.py` 함수화 + CLI 인자 (filter_id override 등) 도입
4. 통합 동작 테스트 (소량 이슈 1~2건으로 main 흐름 + DB 적재 라운드트립)
