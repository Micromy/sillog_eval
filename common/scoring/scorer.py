"""ScorerAsync — DB 직접 적재 버전.

각 issue마다:
1. lookup_task_id (Jira key → task_id). None이면 skip.
2. insert_result_placeholder → task_eval_id (status='PENDING')
3. 정량 평가 (rule registry) + 정성 평가 (LLM, 라운드 루프) + 감독관 검토
4. 성공: populate_result로 본문/items/reviews INSERT + status='DONE'
   실패: mark_result_failed로 status='FAILED' + failed_reason

retry까지 실패한 issue가 누적 SHUTDOWN_THRESHOLD에 도달하면 sys.exit(2).

[총점] 균등 배점 (PASS=1.0, PARTIAL=0.5, FAIL=0.0)
[총평] 감독관 피드백 기반
"""
import time
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_core.runnables import RunnableConfig

from .base import ChecklistResult, IssueScore
from .evaluators.quantitative import QuantitativeEvaluator
from .extractor import SillogDataExtractor
from .agents import CriteriaRefiner, SupervisorAgent
from common.convert import to_raw_dict
from common.constants import EvalMethod, PassFail, RuleType, SCORE_MAP
from common import db
from common.db.result import (
    insert_result_placeholder,
    lookup_task_id,
    mark_result_failed,
    populate_result,
)
from common.db.rules import load_rule_items, load_rule_item_id_map
from common.shutdown import FailureCounter
from common.config import (
    EVALUATE_PROMPT,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY,
    DEFAULT_MAX_WORKERS,
    DEFAULT_MAX_QUAL_WORKERS,
    LLM_TIMEOUT,
    QUAL_BATCH_FUTURE_TIMEOUT,
    ISSUE_TIMEOUT,
    SHUTDOWN_THRESHOLD,
)


# ── 점수 계산 ──────────────────────────────────────

def calc_weighted_score(quant_results, qual_results):
    """균등 배점 점수 (0~100)"""
    all_results = quant_results + qual_results
    if not all_results:
        return 0.0
    total = sum(SCORE_MAP.get(r.pass_fail, 0.0) for r in all_results)
    return round((total / len(all_results)) * 100, 2)


# ── 정성 평가 (병렬 batch) ─────────────────────────

def evaluate_qualitative_batch(
    extracted_data,
    llm_pool,
    target_criteria: Dict[str, str],
    max_workers=DEFAULT_MAX_QUAL_WORKERS,
    max_retries=DEFAULT_MAX_RETRIES,
    retry_delay=DEFAULT_RETRY_DELAY,
    criteria_refinements=None,
    progress_callback=None,
):
    """여러 정성 항목 병렬 평가.

    Args:
        target_criteria: {item_name: criteria_text} (DB의 eval_method='llm' 항목)

    Returns:
        (results: List[ChecklistResult], error_log: List[Dict])
    """
    criteria = target_criteria
    refinements = criteria_refinements or {}
    total = len(criteria)

    print(f"  [정성 평가] {total}개 항목 (worker {min(max_workers, len(llm_pool))}개)")

    items = list(criteria.items())

    def evaluate_one(idx, name, question):
        """단일 항목 평가 (retry 포함)"""
        llm = llm_pool[idx % len(llm_pool)]
        refinement = refinements.get(name, "")
        refinement_section = f"추가 판단 기준: {refinement}" if refinement else ""

        prompt = EVALUATE_PROMPT.format(
            criterion_name=name,
            question=question,
            refinement_section=refinement_section,
            purpose=extracted_data.get("purpose", ""),
            input_data=extracted_data.get("input_data", ""),
            task=extracted_data.get("task", ""),
            output=extracted_data.get("output", ""),
            checklist=extracted_data.get("checklist", ""),
        )

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                config = RunnableConfig(timeout=LLM_TIMEOUT)
                response = llm.invoke(prompt, config=config)
                response_text = response.content if hasattr(response, "content") else str(response)

                json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
                if not json_match:
                    raise ValueError(f"JSON 파싱 실패: {response_text[:200]}")

                result_json = json.loads(json_match.group())
                pass_fail = result_json.get("pass_fail", PassFail.FAIL).upper()
                reasoning = result_json.get("reasoning", "")

                if pass_fail not in SCORE_MAP:
                    pass_fail = PassFail.FAIL

                return pass_fail, reasoning, attempt, None

            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    time.sleep(retry_delay * attempt)

        error_info = {"criterion": name, "error": last_error, "attempts": max_retries}
        return PassFail.FAIL, f"[ERROR] {max_retries}회 시도 실패: {last_error}", max_retries, error_info

    results = []
    error_log = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(evaluate_one, idx, name, question): name
            for idx, (name, question) in enumerate(items)
        }

        completed = 0
        for future in as_completed(futures):
            completed += 1
            name = futures[future]
            question = criteria[name]

            try:
                pass_fail, reasoning, attempts, error_info = future.result(timeout=QUAL_BATCH_FUTURE_TIMEOUT)
                if error_info:
                    error_log.append(error_info)
                retry_note = f" (retry {attempts}회)" if attempts > 1 else ""
                print(f"    [{completed}/{total}] {name}: {pass_fail}{retry_note}")
            except Exception as e:
                pass_fail = PassFail.FAIL
                reasoning = f"[ERROR] future 실패: {e}"
                error_log.append({"criterion": name, "error": str(e), "attempts": 0})
                print(f"    [{completed}/{total}] {name}: ERROR")

            if progress_callback:
                progress_callback(
                    stage="qualitative_evaluation",
                    message=f"{name}: {pass_fail}",
                    progress=(completed / total) * 100,
                    criterion=name,
                )

            results.append(ChecklistResult(
                criterion_name=name,
                question=question,
                pass_fail=pass_fail,
                reasoning=reasoning,
            ))

    return results, error_log


# ── 감독관 검토 (retry wrapper) ────────────────────

def review_with_retry(
    key,
    extracted_data,
    current_score,
    llm_pool,
    round_idx=0,
    max_retries=DEFAULT_MAX_RETRIES,
    retry_delay=DEFAULT_RETRY_DELAY,
):
    """감독관 검토 (호출 실패 시 retry).

    Returns:
        (approved, issues, feedback, supervisor_failed)
    """
    last_error = None

    for attempt in range(1, max_retries + 1):
        llm = llm_pool[(round_idx + attempt - 1) % len(llm_pool)]
        try:
            approved, issues, feedback = SupervisorAgent.review(
                key, extracted_data, current_score, llm,
                stream_console_output=False,
            )
            if attempt > 1:
                print(f"    (감독관 retry {attempt}회 만에 성공)")
            return approved, issues, feedback, False

        except Exception as e:
            last_error = e
            print(f"    [감독관 호출 실패 {attempt}/{max_retries}] {e}")
            if attempt < max_retries:
                time.sleep(retry_delay * attempt)

    return (
        False,
        [],
        f"[감독관 호출 실패] {last_error} ({max_retries}회 시도)",
        True,
    )


# ── 총평 생성 ──────────────────────────────────────

def build_summary(
    approved,
    feedback,
    issues,
    final_score,
    round_num,
    quant_results,
    qual_results,
    error_logs,
    supervisor_failed=False,
):
    """감독관 피드백 기반 최종 총평 + 구조화된 메타.

    Returns:
        (summary_text: str, summary_struct: dict)
    """
    if supervisor_failed:
        status = "supervisor_failed"
        status_label = "감독관 검토 실패"
    elif approved:
        status = "approved"
        status_label = "승인"
    else:
        status = "not_approved"
        status_label = "미승인"

    quant_total = len(quant_results)
    qual_total = len(qual_results)
    quant_pass = sum(1 for r in quant_results if r.pass_fail == PassFail.PASS)
    quant_partial = sum(1 for r in quant_results if r.pass_fail == PassFail.PARTIAL)
    quant_fail = sum(1 for r in quant_results if r.pass_fail == PassFail.FAIL)
    qual_pass = sum(1 for r in qual_results if r.pass_fail == PassFail.PASS)
    qual_partial = sum(1 for r in qual_results if r.pass_fail == PassFail.PARTIAL)
    qual_fail = sum(1 for r in qual_results if r.pass_fail == PassFail.FAIL)

    summary_struct = {
        "final_score": final_score,
        "rounds_used": round_num,
        "supervisor": {
            "status": status,
            "approved": approved,
            "supervisor_failed": supervisor_failed,
            "feedback": feedback or "",
            "issues": issues or [],
        },
        "stats": {
            "quantitative": {
                "total": quant_total,
                "pass": quant_pass,
                "partial": quant_partial,
                "fail": quant_fail,
                "pass_rate": round(quant_pass / quant_total * 100, 2) if quant_total else 0.0,
            },
            "qualitative": {
                "total": qual_total,
                "pass": qual_pass,
                "partial": qual_partial,
                "fail": qual_fail,
                "pass_rate": round(qual_pass / qual_total * 100, 2) if qual_total else 0.0,
            },
        },
        "errors": {
            "count": len(error_logs),
            "items": error_logs,
        },
    }

    parts = [
        f"[감독관 평가: {status_label}]\n"
        f"[최종 점수: {final_score}점 / 라운드: {round_num}회 / 에러: {len(error_logs)}건]",
        "\n[감독관 피드백]",
        feedback or "(피드백 없음)",
    ]

    if issues:
        parts.append(f"\n[지적 사항 ({len(issues)}건)]")
        for i, issue in enumerate(issues, 1):
            parts.append(
                f"{i}. {issue.get('criterion', '?')}\n"
                f"   - 이유: {issue.get('reason', '')}\n"
                f"   - 제안: {issue.get('suggestion', '')}"
            )

    if error_logs:
        parts.append("\n[에러 발생 항목]")
        for e in error_logs:
            parts.append(f"  - {e['criterion']}: {e['error']} ({e['attempts']}회 시도)")

    summary_text = "\n".join(parts)

    return summary_text, summary_struct


# ── 단일 Issue 평가 ────────────────────────────────

def score_issue(
    key: str,
    sillog_data: Any,
    llm_pool: list,
    model_name: str,
    run_id: str,
    eval_rule_set_id: int,
    target_quant: Dict[str, str],
    target_qual: Dict[str, str],
    rule_item_map: Dict[str, int],
    eval_seq: int = 1,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    max_qual_workers: int = DEFAULT_MAX_QUAL_WORKERS,
    progress_callback=None,
) -> Optional[IssueScore]:
    """단일 Issue 평가 + DB 적재.

    Args:
        target_quant: 정량 rule items {item_name: criteria_text}
        target_qual:  정성 rule items {item_name: criteria_text}
        rule_item_map: {item_name: eval_rule_item_id} (자식 적재용)

    Returns:
        IssueScore (DB 적재 성공 시) 또는 None (task_id 매핑 실패 시 skip).
    """
    start_time = time.time()

    # task_id 조회 (skip if 매핑 없음)
    with db.cursor() as cur:
        task_id = lookup_task_id(cur, key)
    if task_id is None:
        print(f"\n[{key}] task_id 매핑 실패 - skip (sillog_tasks_attr에 없음)")
        return None

    # placeholder INSERT (status=PENDING) — 별도 트랜잭션
    with db.cursor() as cur:
        task_eval_id = insert_result_placeholder(
            cur, task_id, eval_rule_set_id, eval_seq, model_name,
        )

    raw_data = to_raw_dict(sillog_data)
    extracted_data = SillogDataExtractor.extract(sillog_data)

    print(f"\n{'='*60}")
    print(f"[{key}] task_id={task_id} task_eval_id={task_eval_id} (seq={eval_seq})")
    print(f"  대상: 정량 {len(target_quant)}개 / 정성 {len(target_qual)}개")
    print(f"{'='*60}")

    try:
        # 1. 정량 평가
        print(f"  [정량 평가]...", end="")
        quant_results = QuantitativeEvaluator().evaluate(target_quant, raw_data)
        print(f" ✓ ({len(quant_results)}개 평가)")

        # 2. 정성 평가 (라운드 루프)
        qual_refinements = {}
        qual_results_map: Dict[str, ChecklistResult] = {}
        target_qual_names = set(target_qual.keys())
        all_error_logs: List[Dict] = []
        review_history: List[Dict] = []
        round_num = 1

        last_feedback = ""
        last_issues: List[Dict] = []
        last_approved = False
        supervisor_failed = False

        for round_num in range(1, max_rounds + 1):
            print(f"\n  --- Round {round_num} ---")

            if round_num == 1:
                target_criteria = target_qual
            else:
                target_criteria = {
                    name: target_qual[name]
                    for name in target_qual_names
                    if name in qual_results_map
                    and (qual_results_map[name].pass_fail != PassFail.PASS
                         or qual_results_map[name].reasoning.startswith("[ERROR]"))
                }
                if not target_criteria:
                    print("  모든 항목 PASS. 재평가 불필요.")
                    break
                print(f"  재평가 대상: {len(target_criteria)}개 항목")

            round_results, round_errors = evaluate_qualitative_batch(
                extracted_data=extracted_data,
                llm_pool=llm_pool,
                target_criteria=target_criteria,
                max_workers=max_qual_workers,
                max_retries=max_retries,
                criteria_refinements=qual_refinements,
                progress_callback=progress_callback,
            )
            all_error_logs.extend(round_errors)

            for r in round_results:
                qual_results_map[r.criterion_name] = r

            current_score = IssueScore(
                key=key,
                round_num=round_num,
                quantitative_results=quant_results,
                qualitative_results=list(qual_results_map.values()),
                total_summary="",
                criteria_refinement_suggestions={},
                elapsed_time=0.0,
            )

            print(f"  [감독 Agent 검토]")
            approved, issues, feedback, supervisor_failed = review_with_retry(
                key, extracted_data, current_score, llm_pool,
                round_idx=round_num - 1,
                max_retries=max_retries,
            )

            review_entry = {
                "round": round_num,
                "eval_seq": eval_seq,
                "approved": approved,
                "supervisor_failed": supervisor_failed,
                "issues": issues or [],
                "feedback": feedback,
                "timestamp": datetime.now().isoformat(),
            }
            review_history.append(review_entry)

            last_feedback = feedback
            last_issues = issues or []
            last_approved = approved

            if supervisor_failed:
                print(f"  ✗ 감독관 검토 실패 - 현재 결과로 확정")
                break

            if approved:
                print(f"  ✓ (승인)")
                break

            print(f"  ✗ (미승인)")
            print(f"  피드백: {feedback}")

            if round_num >= max_rounds:
                print(f"  최대 라운드 도달.")
                break

            refiner_llm = llm_pool[round_num % len(llm_pool)]
            print(f"  [criteria 고도화]...", end="")
            refinement = CriteriaRefiner.refine(
                key, extracted_data, current_score, refiner_llm,
                stream_console_output=False,
            )
            qual_refinements = refinement.get("qualitative_refinements", {})
            print(f" ✓ ({len(qual_refinements)}개)")

        # 3. 최종 점수 + 총평
        qual_results_final = list(qual_results_map.values())
        final_score_value = calc_weighted_score(quant_results, qual_results_final)
        elapsed = time.time() - start_time

        summary_text, summary_struct = build_summary(
            approved=last_approved,
            feedback=last_feedback,
            issues=last_issues,
            final_score=final_score_value,
            round_num=round_num,
            quant_results=quant_results,
            qual_results=qual_results_final,
            error_logs=all_error_logs,
            supervisor_failed=supervisor_failed,
        )

        # 4. DB 적재 (populate)
        items_data = [
            {
                "criterion_name": r.criterion_name,
                "pass_fail": r.pass_fail,
                "reasoning": r.reasoning,
            }
            for r in (quant_results + qual_results_final)
        ]

        with db.cursor() as cur:
            populate_result(
                cur,
                task_eval_id=task_eval_id,
                summary_struct=summary_struct,
                total_summary=summary_text,
                items=items_data,
                review_history=review_history,
                rule_item_map=rule_item_map,
            )

        print(f"\n  최종 점수: {final_score_value}점 | task_eval_id={task_eval_id} | 소요: {elapsed:.1f}초")

        return IssueScore(
            key=key,
            round_num=round_num,
            quantitative_results=quant_results,
            qualitative_results=qual_results_final,
            total_summary=summary_text,
            criteria_refinement_suggestions={"qualitative": qual_refinements},
            elapsed_time=elapsed,
        )

    except Exception as e:
        # 평가 도중 예외 — FAILED로 마킹하고 raise (호출자가 카운터 처리)
        mark_result_failed(task_eval_id, f"score_issue 예외: {e}")
        raise


# ── 일괄 평가 ──────────────────────────────────────

def score_issues_batch(
    items: list,
    llm_pool: list,
    model_name: str,
    run_id: str,
    eval_rule_set_id: int,
    eval_seq: int = 1,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    max_qual_workers: int = DEFAULT_MAX_QUAL_WORKERS,
    max_workers: int = DEFAULT_MAX_WORKERS,
    progress_callback=None,
) -> List[IssueScore]:
    """여러 Issue 일괄 평가.

    각 issue마다 placeholder + populate(또는 mark_failed) 패턴으로 DB 직접 적재.
    누적 실패 SHUTDOWN_THRESHOLD 도달 시 sys.exit(2).

    Args:
        items: [(source_issue_key, sillog_data_dict), ...]
        run_id: parse 실행 ID (재개용)
        eval_rule_set_id: DB의 활성 rule_set_id (caller가 결정)
    """
    if not llm_pool:
        raise ValueError("llm_pool이 비어있습니다")

    # rule items 로드 (DB SOT)
    target_quant = load_rule_items(EvalMethod.RULE)
    target_qual = load_rule_items(EvalMethod.LLM)
    rule_item_map, _ = load_rule_item_id_map()

    print(f"[ScorerAsync] LLM {len(llm_pool)}개 ({model_name}) | 최대 {max_rounds}라운드")
    print(f"  rule items: 정량 {len(target_quant)}개 / 정성 {len(target_qual)}개")
    print(f"[일괄 평가] {len(items)}개 Issue | 동시 {max_workers}개 | run_id={run_id} | rsid={eval_rule_set_id}")

    counter = FailureCounter(threshold=SHUTDOWN_THRESHOLD)
    results: List[IssueScore] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                score_issue,
                key, data, llm_pool, model_name,
                run_id, eval_rule_set_id,
                target_quant, target_qual, rule_item_map,
                eval_seq, max_rounds, max_retries, max_qual_workers, progress_callback,
            ): key
            for key, data in items
        }

        completed = 0
        for future in as_completed(futures):
            completed += 1
            key = futures[future]

            try:
                result = future.result(timeout=ISSUE_TIMEOUT)
                if result is None:
                    # task_id 매핑 실패 — skip (셧다운 카운터에 포함 X)
                    print(f"  [{completed}/{len(items)}] {key}: SKIP (task_id 매핑 없음)")
                    continue
                results.append(result)
                counter.reset()
            except Exception as e:
                reason = f"FATAL 평가 실패: {e}"
                print(f"  [{completed}/{len(items)}] {key}: FATAL ERROR - {e}")
                if counter.bump_failure(reason) >= SHUTDOWN_THRESHOLD:
                    counter.exit("score_issues")

    print(f"[일괄 평가] 완료 ({len(results)}건 성공)")
    return results
