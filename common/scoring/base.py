# -*- coding: utf-8 -*-
"""Scoring 패키지의 dataclass 정의.

체크리스트 항목은 DB의 `eval_task_rule_item` 테이블이 SOT.
`common.db.rules.load_rule_items(eval_method)`로 로드.
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ChecklistResult:
    """체크리스트 결과"""
    criterion_name: str
    question: str
    pass_fail: str
    reasoning: str


@dataclass
class IssueScore:
    """Issue 전체 평가 결과"""
    key: str
    round_num: int
    quantitative_results: List[ChecklistResult] = field(default_factory=list)
    qualitative_results: List[ChecklistResult] = field(default_factory=list)
    total_summary: str = ""
    criteria_refinement_suggestions: Dict = field(default_factory=dict)
    elapsed_time: float = 0.0
