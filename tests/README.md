# Tests — 사내 통합 테스트 시나리오

소량 issue(5~10건)로 사내 환경에서 end-to-end 검증. 모든 테스트는 `run_id LIKE 'test_%'`로 격리되어 운영 데이터에 영향 없음.

## 사전 준비

1. **환경 변수**: `tests/.env.example`을 참고해 다음을 설정.
   ```bash
   export PLATFORM=DTGPT
   export DTGPT_URL=...  DTGPT_MODEL=...  DTGPT_TOKEN=...
   export ORACLE_USER=...  ORACLE_PASSWORD=...  ORACLE_DSN=...
   export SCORER_STORAGE_DIR=~/test_storage_eval
   export TEST_EVAL_RULE_SET_ID=<테스트용 eval_rule_set_id>
   export SHUTDOWN_THRESHOLD=3   # 테스트 중에는 빨리 트리거
   ```

2. **이슈 지정** — 둘 중 하나:
   - `FILTER_ID=<Jira filter ID>`: 저장된 filter 사용 (filter UI로 키 관리)
   - `TEST_JQL="key in (PROJ-1, PROJ-2, PROJ-3)"`: JQL 직접 지정 (filter 안 만들고 빠르게)
   - 둘 다 있으면 `TEST_JQL` 우선 (시나리오의 `run_fetch_jira` 헬퍼가 처리)

3. **테스트용 `eval_rule_set_id`**: 운영용과 분리되어 있으면 가장 안전.

## 시나리오

| 시나리오 | 목적 | 자동/수동 |
|---------|------|-----------|
| `01_cold_path.sh` | 신규 처리 → fetch → parse → score → DB cleanup | 자동 |
| `02_resume.md` | 중단 후 재개 (Ctrl+C 검증) | 수동 |
| `03_shutdown.sh` | LLM 다운 시뮬레이션 + sys.exit(2) | 자동 |
| `04_target_fields.sh` | LLM 평가 필드 제한 동작 검증 | 자동 |

## 안전장치

모든 시나리오:
- `run_id`는 `test_$(date)` 형태로 자동 생성 (운영과 충돌 없음)
- 시작 시 환경 변수 검증 (`TEST_EVAL_RULE_SET_ID` 등 누락 시 즉시 종료)
- 끝에 `cleanup cleanup_test_db --execute --yes`로 DB 정리

**비정상 종료(Ctrl+C, 셧다운) 시에도 정리하려면:**
```bash
python run_task.py cleanup cleanup_test_db --run-id-prefix test_   # dry-run
python run_task.py cleanup cleanup_test_db --run-id-prefix test_ --execute
```

## 중간에 멈추기

각 시나리오 중 Ctrl+C로 멈출 수 있음 (모든 task는 idempotent). 멈춘 뒤:
- 같은 `--run-id`로 task 재실행 → DONE은 skip, PENDING만 처리
- 또는 테스트 끝내려면 cleanup_test_db로 정리

## 검증 SQL

`tests/sql/verify_state.sql` 참고. 주요:
- 처리 결과 status 분포
- 실패 사유 모음
- 자식 row 정합성
- target_fields 컬럼 상태
