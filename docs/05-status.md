# 05. 현재 상태 / TODO

기준일: 2026-05-06. 권위 있는 진행 SOT는 루트 `REFACTORING.md`. 이 문서는 사람이 읽기 좋은 요약 + 운영상 미연동 항목.

## 코드 베이스 상태

- 형태: **task-dispatch 코드베이스** (이전 Airflow `run_task.py` 패턴)
- 루트는 패키지 아님 — top-level package: `common`, `parse`, `score`, `save`
- 진입점: `python run_task.py <dag> <task_id> [args...]`
- 이전 형태(Airflow DAG 모듈) 원격: `https://github.com/Micromy/sillog_eval` (force push로 standalone 버전으로 교체됨, 2026-05-06)

## 리팩토링 진행

| 항목 | 상태 |
|------|------|
| 1-1. `db.fetch_one`/`fetch_all` → `db.fetch`/`db.select` | ✅ |
| 1-2. `task_excution_method` 오타 정정 | ✅ |
| 2-1. 문자열 유틸 → `common/text.py` 추출 | ✅ |
| 2-2. `extractor.py` dict/Pydantic 중복 제거 | ✅ |
| 3-1. 평가 결과 저장 헬퍼 → `score/storage.py` | ✅ |
| 3-2. 패키지화 + entry 함수 통일 (이전 단계) | ✅ → 후속 재구성으로 대체됨 |
| 3-3. `to_raw_dict` → `common/convert.py` | ✅ |
| 4-1. wildcard import 제거 | ✅ |
| 4-2. 타입 힌트 보강 | ✅ |
| 4-3. `parse/llm_parser.py` 에러 수집/리포트 | ✅ |
| **R-1. task-dispatch 구조로 재편성** | ✅ (2026-05-06) |
| **R-2. task entry / common 인터페이스 분리** | ✅ (2026-05-06) |

### R-1: 디렉토리 재편성

- 루트 `__init__.py` 삭제 (루트가 더 이상 패키지 아님)
- 모든 상대 import → 절대 import (`from common.config import ...`)
- 디렉토리: `common/`, `parse/`, `score/`, `save/` (top-level packages)
- task: `parse fetch_jira`, `parse parse_description`, `score score_issues`, `save upload_parsed`, `save upload_results`, `save migrate_meta`, `save reset_results`
- dispatcher `run_task.py`: `sys.argv = [module_path] + sys.argv[3:]` 보정으로 task가 표준 argparse 사용 가능
- `main.py` 삭제 (run_task.py + 3개 task로 분할)
- `parser/`, `scorer/` 디렉토리 → `parse/`, `score/`로 이름 변경

## 미연동 / 운영 갭

- **`.env`** 작성 필요 (커밋 금지). 최소: `PLATFORM`, `DTGPT_*` 또는 `DS_LLM_*`, `FILTER_ID`, `JIRA_*`, `ORACLE_*`, `SCORER_STORAGE_DIR`
- **프롬프트** (`EVALUATE_PROMPT`/`REFINE_PROMPT`/`REVIEW_PROMPT`/`PARSING_TEMPLATE`) — `common/config.py`에 placeholder만, 실제 템플릿은 로컬에서 채워야 함
- **DDL** — `eval_task_parsed*` / `eval_task_result*` / `sillog_tasks_attr` / `eval_task_rule_item` 스키마는 본 레포 외부. 운영 DB 적용 선결 필요
- **`STORAGE_DIR` 기본값**이 Windows 경로(`C:\Users\sh0913.park\...`)로 박혀 있음 — 리눅스에서 돌리려면 env override 필수
- **Jira `verify_ssl=False`** 하드코딩 — 환경 변경이 필요하면 코드 수정

## 다음 작업 추천

1. `.env.example` 작성 + README 셋업 절 추가
2. `STORAGE_DIR` Windows 기본값 → 환경 비종속(상대 경로 또는 None+검증)
3. 통합 동작 테스트 — 사내망에서 3개 task 순차 실행 (`fetch_jira` → `parse_description` → `score_issues`)
4. 운영 DB DDL 적용 + Jira/Oracle/LLM 연결 점검
5. Airflow DAG 파일 작성 (BashOperator로 `python run_task.py <dag> <task_id>` 호출)
