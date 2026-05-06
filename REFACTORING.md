# sillog_eval 코드 정리 기록

코드 리팩토링 진행 상황을 기록한 문서.
정리 완료 후 이 파일은 삭제하거나 docs/로 이동.

---

## 현재 프로젝트 구조

```
sillog_eval/
├── __init__.py                    # (빈 파일)
├── config.py                      # 전역 설정 (프롬프트, LLM 접속정보, 타임아웃 등)
├── DESIGN.md                      # 설계 문서 (10개 섹션 + 부록)
│
├── main.py                        # 메인 진입점 (Jira fetch → 파싱 → 평가)
├── jira.py                        # Jira 연동 (이슈 조회, HTML 섹션 분리)
├── llm.py                         # LLM 클라이언트 팩토리 + safe_structured_invoke
├── models.py                      # Pydantic 모델 (SillogData, Manager, InputData 등)
├── parsing_llm.py                 # LLM 병렬 파싱 (issues → SillogData)
├── storage.py                     # 범용 파일 I/O (pkl, json)
├── score_async.py                 # 평가 엔진 (정량+정성+감독관, 항목별 파일 저장)
│
├── upload_parsed.py               # 로컬 parsed JSON → DB 적재 스크립트
├── migrate_eval_results.py        # 로컬 평가 결과 → DB 마이그레이션
├── migrate_meta.py                # 기존 _meta.json 포맷 마이그레이션
├── reset_eval_results.py          # 평가 결과 테이블 리셋 (dry-run 지원)
│
├── common/
│   ├── __init__.py
│   ├── db.py                      # Oracle 연결/쿼리 헬퍼 (cursor, select, fetch 등)
│   └── text.py                    # ★ 신규 - 문자열/데이터 변환 유틸
│
├── parser/
│   ├── __init__.py
│   └── persistence.py             # eval_task_parsed 계열 적재 (save_parsed, 배치)
│
└── scorer/
    ├── __init__.py                # 패키지 re-export
    ├── base.py                    # 데이터 클래스 (ChecklistResult, IssueScore, 체크리스트)
    ├── agents.py                  # CriteriaRefiner, SupervisorAgent (LLM)
    ├── extractor.py               # SillogDataExtractor (SillogData → 평탄화 텍스트)
    └── evaluators/
        ├── __init__.py
        └── quantitative.py        # QuantitativeEvaluator (Rule 기반 정량 평가)
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

### 2. 중복 제거 🔄 진행 중

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

### 3. 모듈 구조 개선 ⬜ 예정

#### 3-1. storage.py 역할 정리 ✅

루트 `storage.py`(pkl/json 3줄)는 범용 파일 I/O로 유지.
`score_async.py` 내 저장 함수들(`save_item_result`, `save_meta`, `save_iteration`, `load_previous_results` + 경로 헬퍼 `_final_dir`/`_items_dir`/`_iteration_dir`)을 `scorer/storage.py`로 분리.

**변경 파일:**
- `scorer/storage.py` — 신규 (151줄, 4개 public + 3개 private 헬퍼)
- `score_async.py` — 130줄 삭제 (저장 함수 정의 제거), 6줄 import 추가, `from pathlib import Path` 미사용으로 제거 (723줄 → 593줄)

```
refactor: 평가 결과 저장 헬퍼를 scorer/storage.py로 분리
```

#### 3-2. main.py 함수화

스크립트 레벨 코드를 `def main()` + `if __name__ == "__main__"` 패턴으로 감싸기.

#### 3-3. common/ 추가 확장

`to_raw_dict` 등 여러 모듈에서 쓰이는 변환 함수를 `common/convert.py`로 추출 검토.

---

### 4. 코드 품질 ⬜ 예정

- `llm.py`의 `from config import *` wildcard import 제거
- 타입 힌트 보강 (`jira.py`, `storage.py`, `main.py`)
- 에러 핸들링 패턴 통일 (`parsing_llm.py`의 silent skip → 에러 수집/리포트)

---

## 정리 규칙

- 코드 변경 시 커밋 메시지 함께 기록
- 기존 동작은 유지 (리팩토링 only, 기능 변경 없음)
- config.py 민감정보는 문서에 포함하지 않음
