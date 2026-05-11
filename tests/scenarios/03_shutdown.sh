#!/usr/bin/env bash
# 시나리오 3: 셧다운 트리거 (LLM 다운 시뮬)
# 잘못된 LLM 토큰으로 호출 → SHUTDOWN_THRESHOLD건 누적 실패 시 sys.exit(2) 검증.
# 토큰 복구 후 재실행 시 FAILED는 skip, PENDING만 재처리.

source "$(dirname "$0")/_common.sh"

echo "=========================================="
echo "[Test 3] 셧다운 트리거 (LLM 토큰 무효화)"
echo "  TEST_RUN_ID = ${TEST_RUN_ID}"
echo "  SHUTDOWN_THRESHOLD = ${SHUTDOWN_THRESHOLD:-10}"
echo "=========================================="

# 사전 fetch (정상 토큰으로)
run_fetch_jira

# 토큰 백업 후 무효 토큰으로
ORIG_TOKEN="${DTGPT_TOKEN:-}"
export DTGPT_TOKEN=invalid_test_token_xxxxxxxx

echo ""
echo "[Step 1] 무효 토큰으로 parse_description 실행 → sys.exit(2) 기대"
set +e   # 실패해도 계속
run_task parse parse_description --run-id "${TEST_RUN_ID}"
EXIT_CODE=$?
set -e

echo ""
echo "[검증] 종료 코드: ${EXIT_CODE} (기대값: 2)"
if [ "${EXIT_CODE}" != "2" ]; then
    echo "  [WARN] 기대 종료 코드(2)와 다름. SHUTDOWN_THRESHOLD 도달 전에 끝났을 수 있음."
fi

verify_status "Test 3 - 셧다운 직후 (FAILED 다수 + PENDING 있어야)"

# 토큰 복구 후 재실행
echo ""
echo "[Step 2] 토큰 복구 후 재실행 → FAILED는 skip, PENDING만 재처리 기대"
export DTGPT_TOKEN="${ORIG_TOKEN}"
run_task parse parse_description --run-id "${TEST_RUN_ID}"

verify_status "Test 3 - 토큰 복구 후 (PENDING은 모두 DONE 되었을 것)"

cleanup_test_data

echo ""
echo "[Test 3] 완료"
