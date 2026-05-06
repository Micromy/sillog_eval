# 04. 정책 (Policies)

## 1. 설정 / 환경변수

`.env` 로드(`python-dotenv`) 후 `config.py`에서 읽는다. 민감정보는 코드에 포함하지 않는다.

| 변수 | 기본값 | 비고 |
|------|--------|------|
| `PLATFORM` | `DTGPT` | `DTGPT` \| `DS_LLM` |
| `DTGPT_URL`/`DTGPT_MODEL`/`DTGPT_TOKEN` | `""` | DTGPT 사용 시 필수 |
| `DS_LLM_URL`/`DS_LLM_MODEL` | `""` | DS_LLM 사용 시 필수 (헤더는 코드에서 직접) |
| `FILTER_ID` | `""` | Jira 저장된 필터 ID |
| `LLM_POOL_SIZE` | `5` | `main.py`가 만드는 ChatOpenAI 인스턴스 수 |
| `SCORER_STORAGE_DIR` | Windows 경로 | 평가/파싱 결과 루트 |
| `SCORER_LLM_TIMEOUT` | `120` (초) | 단일 LLM 호출 타임아웃 |
| `SCORER_QUAL_BATCH_FUTURE_TIMEOUT` | `300` | 정성 batch future timeout |
| `SCORER_ISSUE_TIMEOUT` | `600` | 단일 Issue 평가 timeout |
| `SCORER_MAX_ROUNDS` | `3` | 정성 평가 라운드 상한 |
| `SCORER_MAX_RETRIES` | `3` | LLM/감독관 retry |
| `SCORER_RETRY_DELAY` | `2.0` | retry exp backoff base |
| `SCORER_MAX_WORKERS` | `3` | 일괄 평가 동시 Issue 수 |
| `SCORER_MAX_QUAL_WORKERS` | `5` | 정성 평가 항목 병렬 수 |
| `JIRA_URL`/`JIRA_USERNAME`/`JIRA_PASSWORD` | — | `jira.py`에서 직접 `os.environ.get` |
| `ORACLE_USER`/`ORACLE_PASSWORD`/`ORACLE_DSN` | — | `common/db.py`에서 필수 |
| `ORACLE_PATH` | optional | thick client 라이브러리 경로 |

## 2. LLM 호출

### 클라이언트 팩토리 (`llm.create_llm`)
- `PLATFORM`에 따라 `ChatOpenAI` 인스턴스 분기 (DTGPT는 `api_key`+`base_url`, DS_LLM은 `default_headers`)
- 풀(`LLM_POOL_SIZE`개)을 미리 만들어 라운드로빈으로 사용

### Structured invoke 폴백 체인 (`safe_structured_invoke`)
1. `llm.with_structured_output(schema).invoke(prompt)`
2. 실패 시 `llm.invoke(prompt)` → 응답에서 ```json``` 제거 후 정규식 `\{.*\}` 추출 → `schema.model_validate_json`
3. 두 시도 모두 실패하면 `retry_delay * attempt` 초 대기 후 재시도 (최대 `max_retries=3`)
4. 전부 실패 → `None` 반환 (호출자에서 실패 처리)

### 정성 평가 LLM 호출 (`evaluate_qualitative_batch`)
- `RunnableConfig(timeout=LLM_TIMEOUT)`을 항상 부여
- 응답에서 `\{.*\}` 정규식 매칭으로 JSON 추출
- `pass_fail` 값이 `SCORE_MAP`(PASS/PARTIAL/FAIL)에 없으면 `FAIL`로 fallback
- 항목 단위 retry (`max_retries`회), 모두 실패 시 결과는 FAIL로 기록 + `error_log`에 누적

### 감독관 호출 (`SupervisorAgent.review` + `review_with_retry`)
- 호출 실패/JSON 누락은 `raise` → wrapper에서 retry 가능
- 정상 응답의 `approved=False`(미승인)는 retry 대상이 아님 (정상 미승인 vs 호출 실패 분리)
- 모든 retry 실패 시 `supervisor_failed=True`로 표시하고 현재 결과 확정

## 3. 점수 정책

- `SCORE_MAP = {"PASS": 1.0, "PARTIAL": 0.5, "FAIL": 0.0}`
- `calc_weighted_score` = **균등 배점** (정량 + 정성 합산 점수 / 항목수 × 100, 소수 둘째자리 반올림)
- 가중치 미적용. 모든 체크리스트 항목 1표.

## 4. 재평가 정책 (`load_previous_results`)

- `_meta.json` 존재 시 재평가 모드, `eval_seq +1`
- `quantitative_checklist` / `qualitative_checklist` 인자에 변경된 항목만 넘기면 해당 항목만 재평가하고 나머지는 이전 결과 유지
- 라운드 ≥2: 아직 PASS 아닌 항목 + reasoning이 `[ERROR]`로 시작하는 항목만 재평가 대상
- `review_history`는 누적 (이전 평가의 history를 이어 받음)

## 5. 정량 룰 정책 (`QuantitativeEvaluator`)

- 채움 비율 기반 점수: 1.0(전부) / 0.5(일부) / 0.0(없음)
- "없음" 판정에 `EMPTY_EXPRESSIONS` (없음/해당없음/n/a/na/tbd/미정/추후/미확인/-) 포함
- `_eval_completion_pass_fail` (현재 정량 체크리스트에서 호출되지는 않으나 헬퍼 보존):
  - `RESULT_PATTERNS`(\d+건/개/%/rows/PASS/FAIL 등) 있으면 결과 기준 인정
  - `BEHAVIOR_KEYWORDS`(확인/검토/리뷰)만 있으면 FAIL
- Manager 점수: `MANAGER_FIELDS = (role, role_type, job_category)` 모두 채워지면 1.0, 일부 0.5, 없으면 0.0

## 6. 저장 정책

### 파일 저장 분리 원칙
- 항목별 파일(`items/{criterion_name}.json`)을 분리해 **부분 업데이트 친화적** (재평가 시 변경 항목만 덮어쓰기)
- 메타(`_meta.json`)는 전체 재작성
- 라운드 스냅샷(`iteration/{key}/seq-N-round-M-{ts}.json`)은 디버깅용, 누적

### DB 저장 정책 (`parser/persistence.py`)
- `with db.cursor()` = 단일 connection / 단일 트랜잭션 / 자동 commit·rollback
- VARCHAR2 컬럼은 모두 `truncate(value, max_bytes)` 거쳐 INSERT (UTF-8 byte 안전 절삭, 초과 시 `...` 추가)
- CLOB 컬럼(`raw_json`/`description`/`item_text`)은 `clob_or_none` (None/빈문자만 None)
- 누락된 필드: 필수(run_id, source_issue_key, sillog_data, parser_version)는 raise, 선택은 NULL INSERT
- task_id는 `(SELECT task_id FROM sillog_tasks_attr WHERE attr_master_id=17 AND attr_value=:issue_key)` 서브쿼리로 자동 매핑

### 배치 적재 (`save_parsed_batch`)
- **건별 트랜잭션**: 한 건 실패해도 다른 건은 진행 (각 `save_parsed` 호출이 독립 transaction)
- 실패 사유는 결과 dict에 누적해 호출자에 반환

### 일괄 적재 (`upload_parsed.py`)
- UK(`uk_parsed` 또는 unique constraint) 위반은 **skip** (이미 적재된 동일 (run_id, source_issue_key))
- 그 외 실패는 `_load_errors_<ts>.json`에 누적 저장

### 리셋 (`reset_eval_results.py`)
- 기본 dry-run, `--execute` 명시해야 실삭제
- 자식 → 부모 순으로 삭제 (`item_review` → `review` → `item` → `result`)

## 7. 에러 / 재시도 정책 정리

| 단계 | 실패 처리 |
|------|-----------|
| Jira fetch | 캐시 PKL 우선, 없으면 호출 (캐시 모드 = 명시적 삭제 전까지 재호출 안함) |
| LLM 파싱 | `safe_structured_invoke` 3회 retry → None → main에서 최대 3 attempt 재시도 |
| 정성 평가 단일 항목 | retry → 모두 실패 시 FAIL + reasoning에 `[ERROR]` prefix + `error_log` |
| 정성 평가 batch future | `QUAL_BATCH_FUTURE_TIMEOUT` 초과 시 FAIL 처리 |
| 감독관 호출 | exception은 retry, `approved=False`는 정상 흐름 |
| 단일 Issue future | `ISSUE_TIMEOUT` 초과 시 FATAL 처리 (round=0, summary에 `[FATAL]`) |
| DB 단건 적재 | 트랜잭션 rollback + raise → 호출자에서 결정 |

## 8. 코드 컨벤션 / 진행 중인 정정

`REFACTORING.md` SOT. 이미 적용된 것:

- `db.fetch_one`/`fetch_all` → `db.fetch`/`db.select`로 호출부 통일
- `task_excution_method` → `task_execution_method` 오타 정정 (models, extractor, persistence)
- 공통 문자열 유틸 `common/text.py` 추출 (`truncate`/`clob_or_none`/`safe_dict`/`safe_list`), `_` private 접두 제거

진행 예정 (현재 미적용):
- `extractor.py` dict/Pydantic 분기 중복 제거 (`to_raw_dict()` 한 번 통과 후 dict 단일 경로)
- `score_async.py`의 저장 함수를 `scorer/storage.py`로 이전, 루트 `storage.py` 역할 정리
- `main.py`를 `def main()` + `if __name__ == "__main__"` 형태로
- `llm.py`의 `from config import *` 명시 import로 변경
- 타입 힌트 / 에러 핸들링 패턴 보강

## 9. 보안 / 자료 취급

- `config.py`는 템플릿. 실제 토큰/URL/프롬프트는 `.env` 또는 로컬 수정본에서 관리하고 **커밋 금지**
- Jira / Oracle 자격은 `os.environ`에서만 읽음 (코드에 하드코딩 X)
- DB 접속 SSL/검증 옵션은 환경에 따름. Jira는 `verify_ssl=False` (사내 인증서 환경 전제)
