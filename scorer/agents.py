# -*- coding: utf-8 -*-
"""
Agent classes - Criteria Refiner, Supervisor Agent

프롬프트와 타임아웃은 루트의 config.py에서 관리.
"""
import re
import json
from typing import Dict, List, Tuple, Any

from langchain_core.runnables import RunnableConfig

from .base import IssueScore, ChecklistResult
from ..config import REFINE_PROMPT, REVIEW_PROMPT, LLM_TIMEOUT


class CriteriaRefiner:
    """
    Criteria 고도화 알고리즘
    이전 평가 결과를 분석하여 criteria를 업데이트
    """

    @staticmethod
    def refine(key, extracted_data, previous_score, llm, stream_console_output=False):
        goal = extracted_data.get("goal", "")
        input_data = extracted_data.get("input_data", "")
        task = extracted_data.get("task", "")
        output = extracted_data.get("output", "")
        completion = extracted_data.get("completion", "")

        quant_str = "\n".join([f"- {r.criterion_name}: {r.pass_fail} ({r.reasoning})" for r in previous_score.quantitative_results])
        qual_str = "\n".join([f"- {r.criterion_name}: {r.pass_fail} ({r.reasoning})" for r in previous_score.qualitative_results])

        prompt = REFINE_PROMPT.format(
            key=key,
            goal=goal,
            input_data=input_data,
            task=task,
            output=output,
            completion=completion,
            quant_results=quant_str,
            qual_results=qual_str,
            summary=previous_score.total_summary,
        )

        try:
            config = RunnableConfig(timeout=LLM_TIMEOUT)
            response = llm.invoke(prompt, config=config)
            response_text = response.content if hasattr(response, 'content') else str(response)

            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {"quantitative_refinements": {}, "qualitative_refinements": {}, "insights": ""}
        except Exception as e:
            print(f"[CriteriaRefiner] LLM 호출 오류: {str(e)}")
            return {"quantitative_refinements": {}, "qualitative_refinements": {}, "insights": f"오류: {str(e)}"}


class SupervisorAgent:
    """
    감독 Agent
    평가 결과를 검토하고 제대로 평가했는지 판단

    호출 실패/응답 형식 오류는 예외로 raise하여 호출자에서 retry 가능하게 한다.
    정상 응답 중 approved=False(미승인)는 그대로 반환.
    """

    @staticmethod
    def review(key, extracted_data, score, llm, stream_console_output=False):
        """
        평가 검토

        Returns:
            (승인 여부, 이슈 리스트, 피드백)

        Raises:
            Exception: LLM 호출 실패 또는 응답 형식 오류 시 (호출자에서 retry 가능)
        """
        goal = extracted_data.get("goal", "")
        input_data = extracted_data.get("input_data", "")
        task = extracted_data.get("task", "")
        output = extracted_data.get("output", "")
        completion = extracted_data.get("completion", "")

        quant_str = "\n".join([f"- {r.criterion_name}: {r.pass_fail} ({r.reasoning})" for r in score.quantitative_results])
        qual_str = "\n".join([f"- {r.criterion_name}: {r.pass_fail} ({r.reasoning})" for r in score.qualitative_results])

        prompt = REVIEW_PROMPT.format(
            key=key,
            goal=goal,
            input_data=input_data,
            task=task,
            output=output,
            completion=completion,
            quant_results=quant_str,
            qual_results=qual_str,
            summary=score.total_summary,
        )

        # 호출 실패는 호출자가 retry할 수 있도록 raise
        config = RunnableConfig(timeout=LLM_TIMEOUT)
        response = llm.invoke(prompt, config=config)
        response_text = response.content if hasattr(response, 'content') else str(response)

        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if not json_match:
            raise ValueError(f"감독관 응답에 JSON 없음: {response_text[:200]}")

        result = json.loads(json_match.group())
        approved = result.get('approved', False)
        issues = result.get('issues', [])
        feedback = result.get('feedback', '')
        return approved, issues, feedback
