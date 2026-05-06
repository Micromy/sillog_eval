# -*- coding: utf-8 -*-
"""
Quantitative Evaluator - Rule-based evaluation
No LLM required, structured field validation
"""
from typing import Dict, List, Tuple, Optional
import re

from common.constants import PassFail
from ..base import QUANTITATIVE_CHECKLIST, ChecklistResult


class QuantitativeEvaluator:
    """정량 평가 - Rule 기반 판단 (구조화된 데이터 기반)"""

    GOAL_OBJECTS = ["기능", "정합성", "오류", "검증", "배포", "연동", "수집", "가공", "삭제", "매핑", "테스트"]
    GOAL_ACTIONS = ["구현", "확보", "방지", "수행", "완료", "적용", "반영", "처리"]
    EMPTY_EXPRESSIONS = ["없음", "해당없음", "해당 없음", "n/a", "na", "tbd", "미정", "추후", "미확인", "-"]
    BEHAVIOR_KEYWORDS = ["확인", "검토", "리뷰"]
    RESULT_PATTERNS = [
        re.compile(r"\d+\s*건"),
        re.compile(r"\d+\s*개"),
        re.compile(r"\d+\s*%"),
        re.compile(r"\d+\s*rows?"),
        re.compile(r"\d+\s*행"),
        re.compile(r"\d+\s*records?"),
        re.compile(r"에러\s*\d+"),
        re.compile(r"error\s*\d+", re.IGNORECASE),
        re.compile(r"\bpass\b", re.IGNORECASE),
        re.compile(r"\bfail\b", re.IGNORECASE),
        re.compile(r"\bsuccess\b", re.IGNORECASE),
    ]

    def __init__(self, criteria_refinements: Optional[Dict] = None):
        self.criteria_refinements = criteria_refinements or {}

    def evaluate(self, data: Dict) -> list[ChecklistResult]:
        description = data.get("description", {})
        input_data_list = description.get("input_data", [])
        outputs_list = data.get("outputs", [])
        checklist = data.get("checklist", [])

        context = {
            "purpose": description.get("purpose", ""),
            "input_data_list": input_data_list,
            "task_manager": description.get("task_manager", {}),
            "outputs_list": outputs_list,
            "checklist": checklist,
        }

        results = []
        for criterion_name, question in QUANTITATIVE_CHECKLIST.items():
            pass_fail, reasoning = self._evaluate_criterion(criterion_name, context)
            results.append(ChecklistResult(
                criterion_name=criterion_name,
                question=question,
                pass_fail=pass_fail,
                reasoning=reasoning,
            ))

        return results

    def _evaluate_criterion(self, criterion_name: str, ctx: Dict) -> Tuple[str, str]:
        evaluators = {
            "input_data_name": lambda: self._eval_list_field(ctx["input_data_list"], "file_name", "Input 데이터명"),
            "input_location": lambda: self._eval_list_field(ctx["input_data_list"], "file_path", "Input 위치"),
            "input_provider": lambda: self._eval_list_managers(ctx["input_data_list"], "managers", "Input 제공자"),
            "task_owner": lambda: self._eval_manager_field(ctx["task_manager"], "Task 담당자"),
            "output_filename": lambda: self._eval_list_field(ctx["outputs_list"], "file_name", "산출물 파일명"),
            "output_location": lambda: self._eval_list_field(ctx["outputs_list"], "file_path", "산출물 위치"),
            "output_receiver": lambda: self._eval_list_managers(ctx["outputs_list"], "receivers", "산출물 수신자"),
        }

        evaluator = evaluators.get(criterion_name)
        if not evaluator:
            return PassFail.FAIL, "알 수 없는 기준입니다."

        score, reasoning = evaluator()

        if score >= 0.8:
            return PassFail.PASS, reasoning
        elif score >= 0.4:
            return PassFail.PARTIAL, reasoning
        else:
            return PassFail.FAIL, reasoning

    def _eval_goal_state(self, purpose: str) -> Tuple[float, str]:
        if not purpose.strip() or purpose.strip().lower() in self.EMPTY_EXPRESSIONS:
            return 0.0, "목적(purpose) 내용이 없어 FAIL"

        for obj in self.GOAL_OBJECTS:
            if obj not in purpose:
                continue
            for act in self.GOAL_ACTIONS:
                if act in purpose:
                    return 1.0, f"'{obj}+{act}' 목적 달성 상태가 포함되어 있어 PASS"

        return 0.0, "목적 달성 상태(object+action 조합)가 없어 FAIL"

    def _eval_list_field(self, items: List[Dict], field: str, label: str) -> Tuple[float, str]:
        if not items:
            return 0.0, f"{label} 항목이 없어 FAIL"

        filled = 0
        total = len(items)

        for item in items:
            value = item.get(field, "").strip()
            if value and value.lower() not in self.EMPTY_EXPRESSIONS:
                filled += 1

        if filled == total:
            return 1.0, f"{label}이 전체 {total}건 모두 작성되어 있어 PASS"
        elif filled > 0:
            return 0.5, f"{label}이 {total}건 중 {filled}건만 작성되어 있어 PARTIAL"
        else:
            return 0.0, f"{label}이 전부 미작성이어서 FAIL"

    def _eval_list_managers(self, items: List[Dict], field: str, label: str) -> Tuple[float, str]:
        if not items:
            return 0.0, f"{label} 항목이 없어 FAIL"

        full_count = 0
        partial_count = 0
        total = len(items)

        for item in items:
            managers = item.get(field, [])
            score = self._best_manager_score(managers)
            if score >= 1.0:
                full_count += 1
            elif score > 0:
                partial_count += 1

        if full_count == total:
            return 1.0, f"{label}이 전체 {total}건 모두 특정 가능하여 PASS"
        elif full_count > 0 or partial_count > 0:
            return 0.5, f"{label}이 {total}건 중 {full_count}건 특정 가능, {partial_count}건 포괄적이어서 PARTIAL"
        else:
            return 0.0, f"{label}이 전부 미작성이어서 FAIL"

    def _eval_manager_field(self, manager: Dict, label: str) -> Tuple[float, str]:
        if not manager:
            return 0.0, f"{label} 정보가 없어 FAIL"

        score = self._manager_score(manager)
        if score >= 1.0:
            return 1.0, f"{label} 정보가 모두 작성되어 특정 가능하여 PASS"
        elif score > 0:
            return 0.5, f"{label} 정보가 일부만 작성되어 포괄적이어서 PARTIAL"
        return 0.0, f"{label} 정보가 없어 FAIL"

    def _eval_completion_pass_fail(self, checklist: List[str]) -> Tuple[float, str]:
        if not checklist:
            return 0.0, "완료조건(checklist)이 없어 FAIL"

        has_result_count = 0
        behavior_only_count = 0

        for item in checklist:
            has_result = any(p.search(item) for p in self.RESULT_PATTERNS)
            has_behavior = any(kw in item for kw in self.BEHAVIOR_KEYWORDS)

            if has_result:
                has_result_count += 1
            elif has_behavior:
                behavior_only_count += 1

        total = len(checklist)

        if has_result_count == total:
            return 1.0, f"완료조건 {total}건 모두 결과 판단 기준이 있어 PASS"
        elif has_result_count > 0:
            return 0.5, f"완료조건 {total}건 중 {has_result_count}건만 결과 기준이 있어 PARTIAL"
        elif behavior_only_count > 0:
            return 0.0, "확인/검토/리뷰 등 행위 기준만 있어 FAIL"
        else:
            return 0.0, "완료조건에 판단 기준이 없어 FAIL"

    CRITERIA_CONTEXT_MIN_LENGTH = 20

    def _eval_completion_criteria_clear(self, checklist: List[str]) -> Tuple[float, str]:
        if not checklist:
            return 0.0, "완료조건(checklist)이 없어 FAIL"

        clear_count = 0
        partial_clear_count = 0
        total = len(checklist)

        for item in checklist:
            item = item.strip()
            if not item or item.lower() in self.EMPTY_EXPRESSIONS:
                continue

            has_result = any(p.search(item) for p in self.RESULT_PATTERNS)

            if has_result and len(item) >= self.CRITERIA_CONTEXT_MIN_LENGTH:
                clear_count += 1
            elif has_result:
                partial_clear_count += 1

        if clear_count == total:
            return 1.0, f"완료조건 {total}건 모두 대상과 기준이 명확하여 PASS"
        elif clear_count > 0 or partial_clear_count > 0:
            return 0.5, f"완료조건 {total}건 중 {clear_count}건 명확, {partial_clear_count}건 맥락 부족하여 PARTIAL"
        else:
            return 0.0, "완료조건에 측정 가능한 기준이 없어 FAIL"

    MANAGER_FIELDS = ("role", "role_type", "job_category")

    @staticmethod
    def _manager_score(manager: Dict) -> float:
        filled = 0
        for key in QuantitativeEvaluator.MANAGER_FIELDS:
            value = manager.get(key, "").strip()
            if value and value.lower() not in QuantitativeEvaluator.EMPTY_EXPRESSIONS:
                filled += 1

        if filled == 3:
            return 1.0
        elif filled > 0:
            return 0.5
        return 0.0

    @staticmethod
    def _best_manager_score(managers: List[Dict]) -> float:
        if not managers:
            return 0.0
        return max(QuantitativeEvaluator._manager_score(m) for m in managers)
