# -*- coding: utf-8 -*-
"""
평가 결과 저장/로드 헬퍼.

[저장 구조]
{storage_dir}/{model_name}/
  final/{key}/
    _meta.json                              ← 전체 메타 (DB의 EVAL_TASK_RESULT)
    items/{criterion}.json                  ← 항목별 결과 (EVAL_TASK_RESULT_ITEM)
  iteration/{key}/
    seq-N-round-M-{ts}.json                 ← 라운드별 스냅샷 (디버깅)
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict

from common.constants import (
    FINAL_SUBDIR,
    ITEMS_SUBDIR,
    ITERATION_SUBDIR,
    META_FILENAME,
    RuleType,
)
from .base import ChecklistResult


# ── 경로 헬퍼 ───────────────────────────────────────

def _final_dir(storage_dir, model_name, key):
    return Path(storage_dir) / model_name / FINAL_SUBDIR / key


def _items_dir(storage_dir, model_name, key):
    return _final_dir(storage_dir, model_name, key) / ITEMS_SUBDIR


def _iteration_dir(storage_dir, model_name, key):
    return Path(storage_dir) / model_name / ITERATION_SUBDIR / key


# ── 저장 ────────────────────────────────────────────

def save_item_result(storage_dir, model_name, key, result, rule_type, eval_seq):
    """항목별 평가 결과 저장 (EVAL_TASK_RESULT_ITEM 매핑)"""
    items_dir = _items_dir(storage_dir, model_name, key)
    items_dir.mkdir(parents=True, exist_ok=True)
    filepath = items_dir / f"{result.criterion_name}.json"

    data = {
        "criterion_name": result.criterion_name,
        "question": result.question,
        "pass_fail": result.pass_fail,
        "reasoning": result.reasoning,
        "rule_type": rule_type,
        "eval_seq": eval_seq,
        "evaluated_at": datetime.now().isoformat(),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(filepath)


def save_meta(storage_dir, model_name, key, score, eval_seq, review_history, summary_struct):
    """전체 메타 정보 저장 (EVAL_TASK_RESULT 매핑)"""
    final_dir = _final_dir(storage_dir, model_name, key)
    final_dir.mkdir(parents=True, exist_ok=True)
    filepath = final_dir / META_FILENAME

    data = {
        "key": key,
        "eval_seq": eval_seq,
        "final_round": score.round_num,
        "elapsed_time": score.elapsed_time,
        "total_summary": score.total_summary,
        "summary": summary_struct,
        "review_history": review_history,
        "timestamp": datetime.now().isoformat(),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(filepath)


def save_iteration(storage_dir, model_name, key, eval_seq, round_num, score, supervisor_entry):
    """라운드별 스냅샷 저장 (디버깅용)"""
    iter_dir = _iteration_dir(storage_dir, model_name, key)
    iter_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = iter_dir / f"seq-{eval_seq}-round-{round_num}-{timestamp}.json"

    def serialize(r):
        return {
            "criterion_name": r.criterion_name,
            "question": r.question,
            "pass_fail": r.pass_fail,
            "reasoning": r.reasoning,
        }

    data = {
        "key": key,
        "eval_seq": eval_seq,
        "round": round_num,
        "timestamp": datetime.now().isoformat(),
        "elapsed_time": score.elapsed_time,
        "supervisor": supervisor_entry,
        "quantitative_results": [serialize(r) for r in score.quantitative_results],
        "qualitative_results": [serialize(r) for r in score.qualitative_results],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(filepath)


# ── 로드 ────────────────────────────────────────────

def load_previous_results(storage_dir, model_name, key):
    """이전 평가 결과 로드 (재평가 시 사용)

    Returns:
        (meta: dict | None, quant_map: Dict[str, ChecklistResult], qual_map: Dict[str, ChecklistResult])
    """
    final_dir = _final_dir(storage_dir, model_name, key)
    items_dir = _items_dir(storage_dir, model_name, key)
    meta_path = final_dir / "_meta.json"

    if not meta_path.exists():
        return None, {}, {}

    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        print(f"[load_previous_results] {key} meta 로드 실패: {e}")
        return None, {}, {}

    quant_map: Dict[str, ChecklistResult] = {}
    qual_map: Dict[str, ChecklistResult] = {}

    if items_dir.exists():
        for item_file in items_dir.glob("*.json"):
            try:
                with open(item_file, encoding="utf-8") as f:
                    item = json.load(f)
                result = ChecklistResult(
                    criterion_name=item["criterion_name"],
                    question=item["question"],
                    pass_fail=item["pass_fail"],
                    reasoning=item["reasoning"],
                )
                if item.get("rule_type") == RuleType.QUANTITATIVE:
                    quant_map[result.criterion_name] = result
                else:
                    qual_map[result.criterion_name] = result
            except Exception as e:
                print(f"[load_previous_results] {item_file.name} 로드 실패: {e}")

    return meta, quant_map, qual_map
