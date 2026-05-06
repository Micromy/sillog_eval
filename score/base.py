# -*- coding: utf-8 -*-
"""
Base classes and constants for Jira Issue scoring system
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Optional


# 정량 평가 기준 (Rule 기반)
QUANTITATIVE_CHECKLIST = {
    "input_data_name": "Input Data명이 작성되어있나요?",
    "input_location": "Input 위치가 명확히 작성되어 있나요?",
    "input_provider": "Input Provider 담당자 정보를 작성했나요? (Project → Champion → Power 형태의 구체적 구분자 포함)",
    "task_owner": "Task Owner 담당자 정보를 작성했나요? (Project → Champion → Power 형태의 구체적 구분자 포함)",
    "output_filename": "산출물 파일명이 작성되어 있나요?",
    "output_location": "산출물 위치가 작성되어 있나요?",
    "output_receiver": "Output Receiver 담당자 정보를 작성했나요? (Project → Champion → Power 형태의 구체적 구분자 포함)",
}

# 정성 평가 기준 (LLM 기반)
QUALITATIVE_CHECKLIST = {
    "goal_state_included": "목적 달성 시 도달하려는 상태가 포함되어있나요? (기능구현, 정합성 확보, 오류 방지, 검증수행 등)",
    "completion_pass_fail": "완료조건 판단기준이 확인/검토/리뷰 등의 행위가 아닌, 결과 달성 여부를 명확히 판단할 수 있는 PASS/FAIL 형태로 작성 되었나요?",
    "completion_criteria_clear": "완료조건 PASS/FAIL 기준은 확인 대상과 검증(기준이 되는 Data(Source)와 값이 동일한지 확인 or 값이 적은지 확인) 조건이 명확히 포함되었나요?",
    "output_validation": "(OUTPUT/VALIDATION) 목적이 Task 산출물 및 완료 조건과 연결이 되나요? (Test 시나리오 작성 → Test Case 목록)",
    "completion_source": "완료조건의 기준이 되는 Data(Source) 위치가 작성되어 있나요? (어디 위치에 있는 어떤 파일에 00열의 무엇을 확인~~)"
}


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
    elapsed_time: float = 0.0  # 평가에 걸린 시간 (초)
