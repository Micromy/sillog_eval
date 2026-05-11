#!/usr/bin/env bash
# 시나리오 1: 신규 처리 (cold path)
# fetch_jira → parse_description → score_issues → verify → cleanup

source "$(dirname "$0")/_common.sh"

echo "=========================================="
echo "[Test 1] Cold path (신규 처리 end-to-end)"
echo "  TEST_RUN_ID = ${TEST_RUN_ID}"
echo "  TEST_EVAL_RULE_SET_ID = ${TEST_EVAL_RULE_SET_ID}"
echo "=========================================="

# 중간에 멈추고 싶으면 Ctrl+C — trap이 cleanup_test_data 호출

run_fetch_jira

run_task parse parse_description --run-id "${TEST_RUN_ID}"

run_task score score_issues \
    --run-id "${TEST_RUN_ID}" \
    --eval-rule-set-id "${TEST_EVAL_RULE_SET_ID}"

verify_status "Test 1 결과"

cleanup_test_data

echo ""
echo "[Test 1] 완료"
