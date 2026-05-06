# 03. 데이터 모델 (Data Model)

## Pydantic 모델 (`models.py`)

```
SillogData
├── description: Description?
│   ├── purpose: str?
│   ├── input_data: list[InputData]?
│   │   └── InputData
│   │       ├── file_name: str?
│   │       ├── file_format: str?
│   │       ├── file_path: str?
│   │       ├── description: str?
│   │       ├── task_link: str?
│   │       └── managers: list[Manager]?
│   ├── task_manager: Manager?
│   ├── task_execution_method: str?
│   └── tool: str?
├── checklist: list[str]?
└── outputs: list[Output]?
    └── Output
        ├── file_name: str?
        ├── file_format: str?
        ├── file_path: str?
        └── receivers: list[Manager]?

Manager
├── role: str?
├── role_type: str?
└── job_category: str?
```

### 모델 정책
- 모든 노드에 `make_fill_nulls()` (`@model_validator(mode="before")`)
  - None / "" / 누락 → 타입에 맞게 보정
    - `list` → `[]`
    - 중첩 BaseModel → `None`
    - 기타 (`str`) → `""`
- `SillogData.checklist`는 list가 아닌 입력도 받음
  - `str` → 줄 단위 split → `list[str]`
  - `list[dict]` → `description`/`title` 우선, 없으면 첫 value 추출
- 필드명: `task_execution_method` (이전 `task_excution_method` 오타 정정됨, 2026-05-06)

## 평가 결과 자료구조 (`scorer/base.py`)

```python
@dataclass
class ChecklistResult:
    criterion_name: str   # 항목 ID (예: "input_data_name", "goal_state_included")
    question: str         # 사람이 읽는 질문문
    pass_fail: str        # "PASS" | "PARTIAL" | "FAIL"
    reasoning: str        # 판단 근거 (룰 텍스트 또는 LLM 응답)

@dataclass
class IssueScore:
    key: str                                      # Jira 이슈 키
    round_num: int                                # 마지막 라운드 번호
    quantitative_results: list[ChecklistResult]
    qualitative_results: list[ChecklistResult]
    total_summary: str                            # 사람이 읽는 총평
    criteria_refinement_suggestions: dict
    elapsed_time: float                           # 초
```

체크리스트 상수:
- `QUANTITATIVE_CHECKLIST`: 7개 (input_data_name, input_location, input_provider, task_owner, output_filename, output_location, output_receiver)
- `QUALITATIVE_CHECKLIST`: 5개 (goal_state_included, completion_pass_fail, completion_criteria_clear, output_validation, completion_source)

## 파일 저장 구조 (평가 결과)

`config.STORAGE_DIR` 하위:

```
{STORAGE_DIR}/
├── jira_issues.pkl                              # Jira fetch 캐시 (main.py)
│
├── parsed/
│   └── {key}.json                               # SillogData.model_dump() (parsing_llm.py)
│
└── {model_name}/
    ├── final/{key}/
    │   ├── _meta.json                           # IssueScore 메타 + summary_struct
    │   └── items/{criterion_name}.json          # 항목별 ChecklistResult + rule_type + eval_seq + evaluated_at
    └── iteration/{key}/
        └── seq-{N}-round-{M}-{ts}.json          # 라운드별 스냅샷 (디버깅)
```

### `_meta.json` 구조 (현재)
```json
{
  "key": "PROJ-1234",
  "eval_seq": 1,
  "final_round": 2,
  "elapsed_time": 87.3,
  "total_summary": "...자연어 텍스트...",
  "summary": {
    "final_score": 75.0,
    "rounds_used": 2,
    "supervisor": {
      "status": "approved | not_approved | supervisor_failed",
      "approved": true,
      "supervisor_failed": false,
      "feedback": "...",
      "issues": [...]
    },
    "stats": {
      "quantitative": {"total": 7, "pass": 5, "partial": 1, "fail": 1, "pass_rate": 71.43},
      "qualitative":  {"total": 5, "pass": 3, "partial": 2, "fail": 0, "pass_rate": 60.0}
    },
    "errors": {"count": 0, "items": []}
  },
  "review_history": [
    {"round": 1, "eval_seq": 1, "approved": false, "supervisor_failed": false,
     "issues": [...], "feedback": "...", "timestamp": "..."},
    ...
  ],
  "timestamp": "2026-05-06T..."
}
```

### `items/{criterion_name}.json` 구조
```json
{
  "criterion_name": "goal_state_included",
  "question": "목적 달성 시 도달하려는 상태가 ...",
  "pass_fail": "PASS",
  "reasoning": "...",
  "rule_type": "QUANTITATIVE | QUALITATIVE",
  "eval_seq": 1,
  "evaluated_at": "2026-05-06T..."
}
```

## DB 모델 (Oracle)

### 파싱 결과 (`eval_task_parsed*`)

```
eval_task_parsed (루트)
├── parsed_id (PK, RETURNING)
├── run_id, task_id (sillog_tasks_attr 서브쿼리로 매핑)
├── raw_json (CLOB)
├── purpose, task_execution_method, tool
├── task_manager_role, task_manager_role_type, task_manager_job_category
├── parsed_at, parser_version

eval_task_parsed_input (parent_id로 _manager가 참조)
├── input_id (PK), parsed_id (FK), seq
└── file_name, file_format, file_path, description (CLOB), task_link

eval_task_parsed_output
├── output_id (PK), parsed_id (FK), seq
└── file_name, file_format, file_path

eval_task_parsed_check
└── parsed_id (FK), seq, item_text (CLOB)

eval_task_parsed_manager (input/output의 담당자)
├── parsed_id (FK), parent_type ('INPUT' | 'OUTPUT'), parent_id, seq
└── role, role_type, job_category
```

**컬럼 길이 정책** (`common/text.truncate(value, max_bytes)`):
| 컬럼 | bytes |
|------|-------|
| purpose | 2000 |
| task_execution_method | 4000 |
| tool | 200 |
| task_manager_role / input/output.file_path / task_link | 1000~2000 |
| role | 200 |
| role_type / job_category / file_format | 50~100 |
| file_name | 500 |
| description / item_text / raw_json | CLOB (`clob_or_none`) |

`save_parsed` 호출부에서 `safe_dict`/`safe_list`로 None/타입 안전화 후 INSERT.

### 평가 결과 (`eval_task_result*`)

`migrate_eval_results.py` / `reset_eval_results.py`가 다루는 4개 테이블 (스키마 자체 정의는 본 레포 외):
- `eval_task_result` (부모, 메타) — `(task_id, eval_rule_set_id, eval_seq)` 단위
- `eval_task_result_item` (자식, 항목별 결과) — 로컬 `criterion_name` ↔ `eval_task_rule_item.item_name`
- `eval_task_result_review` (자식, 라운드별 피드백)
- `eval_task_result_item_review` (자식, 지적사항)

매핑 규칙: avail='Y'인 rule_item만 적재 대상, `eval_rule_set_id`는 매핑된 항목들의 max값.
