"""
ScorerAsync v4 (함수형, 항목별 파일 저장)

[기능 요약]
- 정량 평가: raw 데이터 기반, 1회만 실행 (룰 기반)
- 정성 평가: 평탄화 데이터 기반, 라운드별 실패 항목만 재평가
- 감독관 검토: 호출 실패 시 retry (정상 미승인과 구분)
- 총점: 균등 배점 (PASS=1.0, PARTIAL=0.5, FAIL=0.0)
- 총평: 감독관 피드백 기반
- 저장: 항목별 파일 분리 (DB 매핑 친화적, 부분 업데이트 용이)

[저장 구조]
{storage_dir}/{model_name}/
  final/{key}/
    _meta.json                              ← 전체 메타 (DB의 EVAL_TASK_RESULT)
    items/{criterion}.json                  ← 항목별 결과 (EVAL_TASK_RESULT_ITEM)
  iteration/{key}/
    seq-N-round-M-{ts}.json                 ← 라운드별 스냅샷 (디버깅)

[부분 재평가]
- quantitative_checklist / qualitative_checklist 인자에 변경된 체크리스트만 넘기면
  해당 항목만 평가하고 나머지는 이전 결과 보존
- eval_seq 자동 +1

[설정]
모든 기본값은 루트의 config.py에서 관리. 환경변수로 오버라이드 가능.
"""
import time
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_core.runnables import RunnableConfig

from scorer import (
    ChecklistResult,
    IssueScore,
    QuantitativeEvaluator,
    QUANTITATIVE_CHECKLIST,
    QUALITATIVE_CHECKLIST,
    SillogDataExtractor,
    CriteriaRefiner,
    SupervisorAgent,
)
from scorer.storage import (
    save_item_result,
    save_meta,
    save_iteration,
    load_previous_results,
)
from config import (
    SCORE_MAP,
    EVALUATE_PROMPT,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY,
    DEFAULT_MAX_WORKERS,
    DEFAULT_MAX_QUAL_WORKERS,
    STORAGE_DIR,
    LLM_TIMEOUT,
    QUAL_BATCH_FUTURE_TIMEOUT,
    ISSUE_TIMEOUT,
)


# ── 데이터 변환 헬퍼 ────────────────────────────────

def to_raw_dict(sillog_data):
    """SillogData를 정량 평가용 raw dict로 변환"""
    if isinstance(sillog_data, dict):
        return sillog_data
    if hasattr(sillog_data, "model_dump"):
        return sillog_data.model_dump()
    if hasattr(sillog_data, "dict"):
        return sillog_data.dict()
    raise TypeError(f"sillog_data를 dict로 변환할 수 없음: {type(sillog_data)}")


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
    target_criteria=None,
    max_workers=DEFAULT_MAX_QUAL_WORKERS,
    max_retries=DEFAULT_MAX_RETRIES,
    retry_delay=DEFAULT_RETRY_DELAY,
    criteria_refinements=None,
    progress_callback=None,
):
    """여러 정성 항목 병렬 평가

    Returns:
        (results: List[ChecklistResult], error_log: List[Dict])
    """
    criteria = target_criteria or QUALITATIVE_CHECKLIST
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
            goal=extracted_data.get("goal", ""),
            input_data=extracted_data.get("input_data", ""),
            task=extracted_data.get("task", ""),
            output=extracted_data.get("output", ""),
            completion=extracted_data.get("completion", ""),
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
                pass_fail = result_json.get("pass_fail", "FAIL").upper()
                reasoning = result_json.get("reasoning", "")

                if pass_fail not in SCORE_MAP:
                    pass_fail = "FAIL"

                return pass_fail, reasoning, attempt, None

            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    time.sleep(retry_delay * attempt)

        error_info = {"criterion": name, "error": last_error, "attempts": max_retries}
        return "FAIL", f"[ERROR] {max_retries}회 시도 실패: {last_error}", max_retries, error_info

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
                pass_fail = "FAIL"
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
    """감독관 검토 (호출 실패 시 retry)

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
    """감독관 피드백 기반 최종 총평 + 구조화된 메타 데이터

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
    quant_pass = sum(1 for r in quant_results if r.pass_fail == "PASS")
    quant_partial = sum(1 for r in quant_results if r.pass_fail == "PARTIAL")
    quant_fail = sum(1 for r in quant_results if r.pass_fail == "FAIL")
    qual_pass = sum(1 for r in qual_results if r.pass_fail == "PASS")
    qual_partial = sum(1 for r in qual_results if r.pass_fail == "PARTIAL")
    qual_fail = sum(1 for r in qual_results if r.pass_fail == "FAIL")

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
    key,
    sillog_data,
    llm_pool,
    model_name,
    storage_dir=STORAGE_DIR,
    quantitative_checklist=None,
    qualitative_checklist=None,
    max_rounds=DEFAULT_MAX_ROUNDS,
    max_retries=DEFAULT_MAX_RETRIES,
    max_qual_workers=DEFAULT_MAX_QUAL_WORKERS,
    progress_callback=None,
):
    """단일 Issue 평가 (디버깅/단건 처리용 외부 노출)"""
    start_time = time.time()

    target_quant = quantitative_checklist if quantitative_checklist is not None else QUANTITATIVE_CHECKLIST
    target_qual = qualitative_checklist if qualitative_checklist is not None else QUALITATIVE_CHECKLIST

    prev_meta, prev_quant_map, prev_qual_map = load_previous_results(storage_dir, model_name, key)
    is_reevaluation = prev_meta is not None
    eval_seq = (prev_meta.get("eval_seq", 0) + 1) if is_reevaluation else 1

    raw_data = to_raw_dict(sillog_data)
    extracted_data = SillogDataExtractor.extract(sillog_data)

    print(f"\n{'='*60}")
    mode_label = f"재평가 (seq={eval_seq})" if is_reevaluation else f"신규 평가 (seq=1)"
    print(f"[{key}] {mode_label}")
    print(f"  대상: 정량 {len(target_quant)}개 / 정성 {len(target_qual)}개")
    print(f"{'='*60}")

    # 1. 정량 평가
    print(f"  [정량 평가]...", end="")
    all_quant_results = QuantitativeEvaluator().evaluate(raw_data)
    target_quant_names = set(target_quant.keys())
    new_quant_results = [r for r in all_quant_results if r.criterion_name in target_quant_names]
    print(f" ✓ ({len(new_quant_results)}개 평가)")

    quant_results_map = dict(prev_quant_map)
    for r in new_quant_results:
        quant_results_map[r.criterion_name] = r
        save_item_result(storage_dir, model_name, key, r, "QUANTITATIVE", eval_seq)
    quant_results = list(quant_results_map.values())

    # 2. 정성 평가 (라운드 루프)
    qual_refinements = {}
    qual_results_map: Dict[str, ChecklistResult] = dict(prev_qual_map)
    target_qual_names = set(target_qual.keys())
    all_error_logs: List[Dict] = []
    review_history: List[Dict] = list(prev_meta.get("review_history", [])) if is_reevaluation else []
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
                and (qual_results_map[name].pass_fail != "PASS"
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
            save_item_result(storage_dir, model_name, key, r, "QUALITATIVE", eval_seq)

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

        saved_iter = save_iteration(
            storage_dir, model_name, key, eval_seq, round_num,
            current_score, review_entry,
        )

        if supervisor_failed:
            print(f"  ✗ 감독관 검토 실패 - 현재 결과로 확정")
            print(f"  라운드 결과 저장: {saved_iter}")
            break

        if approved:
            print(f"  ✓ (승인)")
            print(f"  라운드 결과 저장: {saved_iter}")
            break

        print(f"  ✗ (미승인)")
        print(f"  피드백: {feedback}")
        print(f"  라운드 결과 저장: {saved_iter}")

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

    final = IssueScore(
        key=key,
        round_num=round_num,
        quantitative_results=quant_results,
        qualitative_results=qual_results_final,
        total_summary=summary_text,
        criteria_refinement_suggestions={"qualitative": qual_refinements},
        elapsed_time=elapsed,
    )

    saved_meta = save_meta(
        storage_dir, model_name, key, final, eval_seq, review_history,
        summary_struct,
    )
    print(f"\n  최종 점수: {final_score_value}점 | seq={eval_seq} | 소요: {elapsed:.1f}초")
    print(f"  저장: {saved_meta}")

    return final


# ── 일괄 평가 ──────────────────────────────────────

def score_issues_batch(
    items,
    llm_pool,
    model_name,
    storage_dir=STORAGE_DIR,
    quantitative_checklist=None,
    qualitative_checklist=None,
    max_rounds=DEFAULT_MAX_ROUNDS,
    max_retries=DEFAULT_MAX_RETRIES,
    max_qual_workers=DEFAULT_MAX_QUAL_WORKERS,
    max_workers=DEFAULT_MAX_WORKERS,
    progress_callback=None,
):
    """여러 Issue 일괄 평가"""
    if not llm_pool:
        raise ValueError("llm_pool이 비어있습니다")

    print(f"[ScorerAsync] LLM {len(llm_pool)}개 ({model_name}) | 최대 {max_rounds}라운드")
    print(f"[일괄 평가] {len(items)}개 Issue | 동시 {max_workers}개")

    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                score_issue,
                key, data, llm_pool, model_name,
                storage_dir,
                quantitative_checklist, qualitative_checklist,
                max_rounds, max_retries, max_qual_workers, progress_callback,
            ): key
            for key, data in items
        }

        completed = 0
        for future in as_completed(futures):
            completed += 1
            key = futures[future]

            try:
                result = future.result(timeout=ISSUE_TIMEOUT)
            except Exception as e:
                result = IssueScore(
                    key=key, round_num=0,
                    quantitative_results=[], qualitative_results=[],
                    total_summary=f"[FATAL] 평가 실패: {e}",
                    criteria_refinement_suggestions={}, elapsed_time=0.0,
                )
                print(f"  [{completed}/{len(items)}] {key}: FATAL ERROR - {e}")

            results.append(result)

    print(f"[일괄 평가] 완료 ({len(results)}건)")
    return results
