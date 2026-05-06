import time
import re
from langchain_openai import ChatOpenAI
from .config import *


def create_llm():
    if PLATFORM == "DTGPT":
        return ChatOpenAI(
            model=DTGPT_MODEL,
            api_key=DTGPT_TOKEN,
            base_url=DTGPT_URL,
        )
    elif PLATFORM == "DS_LLM":
        return ChatOpenAI(
            base_url=DS_LLM_URL,
            model=DS_LLM_MODEL,
            default_headers=DS_LLM_HEADER,
        )
    else:
        raise ValueError(f"Unknown LLM platform: {PLATFORM}")


def safe_structured_invoke(llm, prompt, schema, max_retries=3, retry_delay=2.0):
    """
    1차: with_structured_output
    2차: 수동 JSON 파싱
    3차: retry
    전부 실패 시: None 반환
    """
    last_error = None

    for attempt in range(1, max_retries + 1):
        # 1차: with_structured_output
        try:
            structured_llm = llm.with_structured_output(schema)
            return structured_llm.invoke(prompt)
        except Exception as e:
            last_error = e

        # 2차: fallback 수동 파싱
        try:
            response = llm.invoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)

            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"```\s*", "", text)
            text = text.strip()

            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return schema.model_validate_json(match.group())
        except Exception as e:
            last_error = e

        # retry 대기
        if attempt < max_retries:
            print(f"    [retry {attempt}/{max_retries}] {str(last_error)[:80]}")
            time.sleep(retry_delay * attempt)

    # 전부 실패
    print(f"    [ERROR] {max_retries}회 시도 실패: {str(last_error)[:100]}")
    return None
