# 05. 현재 상태 / TODO

기준일: 2026-05-07. 권위 있는 진행 SOT는 루트 `REFACTORING.md`. 이 문서는 사람이 읽기 좋은 요약 + 운영상 미연동 항목.

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
| **R-3. 하드코딩 상수 중앙화 (constants.py + db/schema.py)** | ✅ (2026-05-06) |
| **R-4. rule item DB SOT 통합 + Quantitative registry 패턴** | ✅ (2026-05-06) |
| **R-5. API 셧다운 + 재개 + DB 직접 적재 (로컬 결과 파일 제거)** | ✅ (2026-05-07) |

### R-5: API 셧다운 + 재개 + DB SOT

- DDL 변경: `eval_task_parsed`, `eval_task_result`에 `status VARCHAR2(20)`, `failed_reason VARCHAR2(4000)` 컬럼 추가 (사내 DBA 적용 완료)
- 새 패턴: placeholder INSERT (status='PENDING') → LLM 호출 → 성공 populate (status='DONE') / 실패 mark_failed (status='FAILED' + failed_reason)
- 재개: 같은 `--run-id`로 재호출 시 DB의 status='DONE' row를 skip
- 셧다운: 한 issue retry 3회 후 실패가 누적 SHUTDOWN_THRESHOLD(default 10)에 도달하면 sys.exit(2)
- 로컬 결과 파일 모두 제거 (parsed/, _meta.json, items/, iteration/, _parse_errors_*, _load_errors_*) — 유일한 로컬 파일은 `jira_issues.pkl`
- 새 cleanup task (`cleanup cleanup_files`): jira_issues.pkl + 옛 디렉토리 정리

## 미연동 / 운영 갭

- **`.env`** 작성 필요 (커밋 금지). 최소: `PLATFORM`, `DTGPT_*` 또는 `DS_LLM_*`, `FILTER_ID`, `JIRA_*`, `ORACLE_*`, `SCORER_STORAGE_DIR`, `SHUTDOWN_THRESHOLD`(선택)
- **프롬프트** (`EVALUATE_PROMPT`/`REFINE_PROMPT`/`REVIEW_PROMPT`/`PARSING_TEMPLATE`) — `common/config.py`에 placeholder만
- **DDL R-5**: `ALTER TABLE eval_task_parsed/result ADD status/failed_reason` + 인덱스 운영 DB 적용 완료 가정
- **`STORAGE_DIR` 기본값**이 Windows 경로 — 리눅스에서 돌리려면 env override 필수
- **Jira `verify_ssl=False`** — `JIRA_VERIFY_SSL` env로 제어

## 다음 작업 추천

1. `.env.example` 작성 + README 셋업 절 추가
2. `STORAGE_DIR` Windows 기본값 → 환경 비종속(상대 경로 또는 None+검증)
3. 통합 동작 테스트 — 사내망에서 3개 task 순차 실행 (`fetch_jira` → `parse_description` → `score_issues`)
4. 운영 DB DDL 적용 + Jira/Oracle/LLM 연결 점검
5. Airflow DAG 파일 작성 (BashOperator로 `python run_task.py <dag> <task_id>` 호출)
