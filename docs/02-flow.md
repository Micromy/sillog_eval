# 02. 플로우 (Flow)

## End-to-end (main.py)

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. config 로드 (.env → PLATFORM, FILTER_ID, STORAGE_DIR, ...)       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Jira fetch                                                       │
│    - jira_issues.pkl 캐시 우선 (있으면 재사용)                       │
│    - get_jql_filter(FILTER_ID) → JQL                                │
│    - get_sections_by_key(jql) → {key: {description, checklist,     │
│                                          outputs}} (HTML 섹션 분리) │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. LLM 풀 생성 (LLM_POOL_SIZE개)                                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. 병렬 파싱 (parse_issues_parallel) — 최대 3회 재시도 루프          │
│    - PARSING_TEMPLATE.invoke({sections}) → prompt                   │
│    - safe_structured_invoke(llm, prompt, SillogData)                │
│    - {STORAGE_DIR}/parsed/{key}.json 저장                           │
│    - 실패 key만 다음 attempt로 carry-over                           │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 5. 일괄 평가 (score_issues_batch)                                   │
│    - ThreadPoolExecutor(DEFAULT_MAX_WORKERS) → score_issue 병렬    │
└─────────────────────────────────────────────────────────────────────┘
```

## 단일 Issue 평가 (`score_issue`)

```
[load_previous_results]
  ├─ _meta.json 있음 → 재평가 (eval_seq +1)
  └─ 없음           → 신규 평가 (eval_seq=1)
        │
        ▼
[1. 정량 평가] (LLM 무사용, 룰 기반)
  - QuantitativeEvaluator().evaluate(raw_dict) → list[ChecklistResult]
  - quant_results_map[criterion] = result
  - save_item_result(.., rule_type="QUANTITATIVE", eval_seq)
        │
        ▼
[2. 정성 평가 라운드 루프] (max_rounds=3)
  ┌──────────────────────────────────────────────────┐
  │ round_num=1: target = QUALITATIVE_CHECKLIST 전체 │
  │ round_num>1: target = (PASS 아니거나 ERROR인 것) │
  │              없으면 break                        │
  │                                                  │
  │ evaluate_qualitative_batch(...)                  │
  │   ThreadPool(DEFAULT_MAX_QUAL_WORKERS)           │
  │   각 항목당 EVALUATE_PROMPT → JSON               │
  │   retry max_retries회                            │
  │                                                  │
  │ qual_results_map[criterion] = result             │
  │ save_item_result(.., "QUALITATIVE", eval_seq)    │
  │                                                  │
  │ [감독관 검토] review_with_retry                  │
  │   SupervisorAgent.review → (approved, issues,    │
  │                              feedback)            │
  │   호출 실패는 retry, 정상 미승인은 그대로         │
  │                                                  │
  │ save_iteration(round 스냅샷)                     │
  │                                                  │
  │ supervisor_failed → 현재 결과로 확정 후 break    │
  │ approved=True    → break                         │
  │ approved=False:                                  │
  │   if round_num >= max_rounds: break              │
  │   CriteriaRefiner.refine → qual_refinements 갱신 │
  │   다음 라운드로                                  │
  └──────────────────────────────────────────────────┘
        │
        ▼
[3. 최종 점수 + 총평]
  - calc_weighted_score(quant + qual) → 0~100 (균등 배점, PASS=1.0/PARTIAL=0.5/FAIL=0)
  - build_summary(...) → (text, struct)
  - save_meta(score, eval_seq, review_history, summary_struct) → _meta.json
```

## 정량 평가 룰 (`QuantitativeEvaluator`)

7개 항목 모두 데이터 채움 비율 기반 (LLM 미사용):

| 항목 | 판단 |
|------|------|
| `input_data_name` | input_data 리스트의 file_name 채움 비율 |
| `input_location` | input_data의 file_path 채움 비율 |
| `input_provider` | input_data의 managers 정보 (3필드 모두 ↔ 일부 ↔ 없음) |
| `task_owner` | description.task_manager 3필드 채움 |
| `output_filename` | outputs의 file_name 채움 비율 |
| `output_location` | outputs의 file_path 채움 비율 |
| `output_receiver` | outputs의 receivers 정보 |

**점수**: 전체 채움 → 1.0(PASS), 일부 → 0.5(PARTIAL), 없음 → 0.0(FAIL).
"없음" 판정에는 `EMPTY_EXPRESSIONS`(없음/해당없음/n/a/tbd/-/...) 포함.

## 정성 평가 5개 항목 (`QUALITATIVE_CHECKLIST`)

`goal_state_included`, `completion_pass_fail`, `completion_criteria_clear`, `output_validation`, `completion_source` — LLM이 `EVALUATE_PROMPT`에 평탄화된 컨텍스트(goal/input_data/task/output/completion)를 넣어 PASS/PARTIAL/FAIL + reasoning JSON으로 응답.

라운드 2+에서는 `CriteriaRefiner`가 만든 `qualitative_refinements[name]`을 프롬프트의 `refinement_section`에 합쳐 LLM에 더 구체적인 판단 기준 제공.

## 파싱 결과 DB 적재 (`save_parsed`)

`with db.cursor()` 단일 트랜잭션 안에서:

```
1. eval_task_parsed       INSERT … RETURNING parsed_id
   (sillog_tasks_attr WHERE attr_master_id=17 AND attr_value=:issue_key
    서브쿼리로 task_id 자동 매핑)

2. eval_task_parsed_input  INSERT … RETURNING input_id  (×N)
   └ eval_task_parsed_manager INSERT (parent_type='INPUT', parent_id=input_id) (×M)

3. eval_task_parsed_output INSERT … RETURNING output_id (×N)
   └ eval_task_parsed_manager INSERT (parent_type='OUTPUT', parent_id=output_id) (×M)

4. eval_task_parsed_check  INSERT (×N)
```

성공 시 commit, 어느 단계든 예외 → 전체 rollback.

## 운영 스크립트 흐름

### `upload_parsed.py`
`STORAGE_DIR/parsed/*.json` 발견 → 각 파일에 대해 `validate_sillog_structure` (warning) → `save_parsed` 호출. UK 위반은 skip, 그 외 실패는 `_load_errors_<ts>.json`에 누적.

### `migrate_eval_results.py`
`STORAGE_DIR/{model_name}/final/{key}/` 발견 → 로컬 `criterion_name`을 DB `eval_task_rule_item.item_name`에 매핑(avail='Y') → 같은 (task_id, eval_rule_set_id, eval_seq) 발견 시 자식부터 삭제 후 재적재.

### `migrate_meta.py`
기존 `_meta.json`에 `summary` 구조 필드(stats/supervisor 등)를 items 폴더 재계산으로 백필. `.bak` 백업 → dry-run 지원.

### `reset_eval_results.py`
`eval_task_result*`를 `--rule-set-id` (+ 옵션 `--model-name`/`--created-by`) 기준 삭제. 기본 dry-run, `--execute` 명시해야 실삭제.
