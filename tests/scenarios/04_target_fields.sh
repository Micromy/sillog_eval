#!/usr/bin/env bash
# 시나리오 4: target_fields로 LLM 평가 필드 제한 검증.
# DB에서 특정 rule_item의 target_fields를 변경 → score 실행 →
# 평가 결과 reasoning(comment_summary)으로 LLM이 받은 context 추론.
# 끝에 target_fields 원복 + 데이터 정리.

source "$(dirname "$0")/_common.sh"

TARGET_ITEM="${TEST_TARGET_ITEM:-goal_state_included}"

echo "=========================================="
echo "[Test 4] target_fields LLM 필드 제한"
echo "  TEST_RUN_ID = ${TEST_RUN_ID}"
echo "  TARGET_ITEM = ${TARGET_ITEM}"
echo "=========================================="

echo ""
echo "[Step 1] 원본 target_fields 백업"
ORIG_VAL=$(python - <<EOF
from common import db
row = db.fetch(
    "SELECT target_fields FROM eval_task_rule_item WHERE item_name = :n",
    n="${TARGET_ITEM}",
)
print(row['target_fields'] if row and row.get('target_fields') else "")
EOF
)
echo "  original = '${ORIG_VAL}'"

echo ""
echo "[Step 2] target_fields='purpose'로 임시 변경"
python - <<EOF
from common import db
with db.cursor() as cur:
    cur.execute(
        "UPDATE eval_task_rule_item SET target_fields = :tf WHERE item_name = :n",
        tf="purpose", n="${TARGET_ITEM}",
    )
print(f"UPDATE 완료: target_fields = 'purpose' for ${TARGET_ITEM}")
EOF

echo ""
echo "[Step 3] 파이프라인 실행"
run_fetch_jira
run_task parse parse_description --run-id "${TEST_RUN_ID}"
run_task score score_issues \
    --run-id "${TEST_RUN_ID}" \
    --eval-rule-set-id "${TEST_EVAL_RULE_SET_ID}"

echo ""
echo "[Step 4] ${TARGET_ITEM} 항목의 평가 reasoning 확인"
python - <<EOF
from common import db
rows = db.select(
    """
    SELECT p.source_issue_key, i.comment_summary
    FROM eval_task_result_item i
    JOIN eval_task_result r ON i.task_eval_id = r.task_eval_id
    JOIN eval_task_parsed p ON p.task_id = r.task_id
    JOIN eval_task_rule_item ri ON ri.eval_rule_item_id = i.eval_rule_item_id
    WHERE p.run_id = :rid
      AND ri.item_name = :item
    ORDER BY p.source_issue_key
    """,
    rid="${TEST_RUN_ID}",
    item="${TARGET_ITEM}",
)
print(f"\n  {len(rows)}개 평가 결과:")
for r in rows:
    summary = (r['comment_summary'] or '')[:120].replace('\n', ' ')
    print(f"    [{r['source_issue_key']}] {summary}...")
print(f"\n  → reasoning에서 LLM이 [Input 데이터]/[Task 정보]/[Output]/[완료 조건]을")
print(f"    언급하지 않으면 정상 (purpose만 받았기 때문).")
EOF

verify_status "Test 4 - 평가 결과 상태 분포"

echo ""
echo "[Step 5] target_fields 원복"
python - <<EOF
from common import db
orig = "${ORIG_VAL}" or None
with db.cursor() as cur:
    cur.execute(
        "UPDATE eval_task_rule_item SET target_fields = :tf WHERE item_name = :n",
        tf=orig, n="${TARGET_ITEM}",
    )
print(f"UPDATE 원복 완료: target_fields = {orig!r}")
EOF

cleanup_test_data

echo ""
echo "[Test 4] 완료"
