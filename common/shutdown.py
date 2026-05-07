# -*- coding: utf-8 -*-
"""셧다운 트리거 헬퍼.

한 issue 단위 LLM 호출은 `safe_structured_invoke` 안에서 retry 3회. 그래도
실패한 issue가 누적 N건(SHUTDOWN_THRESHOLD)이면 LLM 서버 다운으로 간주하고
남은 issue 처리 없이 task 자체 종료.

병렬 처리(ThreadPoolExecutor)에서도 안전하게 카운트하기 위해 Lock 사용.
"""
import sys
import threading
from typing import Optional


SHUTDOWN_EXIT_CODE = 2


class FailureCounter:
    """thread-safe 누적 실패 카운터.

    Usage:
        counter = FailureCounter(threshold=10)
        ...
        if result is None:
            counter.bump_failure("LLM None 반환")
            if counter.should_shutdown():
                counter.exit("...")  # sys.exit(2) + 콘솔 메시지
        else:
            counter.reset()
    """

    def __init__(self, threshold: int):
        self._threshold = threshold
        self._count = 0
        self._lock = threading.Lock()
        self._last_reason: Optional[str] = None

    def bump_failure(self, reason: Optional[str] = None) -> int:
        """실패 카운터 +1. 현재 누적 건수 반환."""
        with self._lock:
            self._count += 1
            if reason:
                self._last_reason = reason
            return self._count

    def reset(self) -> None:
        """성공 시 0으로."""
        with self._lock:
            self._count = 0

    def should_shutdown(self) -> bool:
        with self._lock:
            return self._count >= self._threshold

    def current(self) -> int:
        with self._lock:
            return self._count

    def exit(self, label: str = "task") -> None:
        """셧다운 메시지 출력 후 sys.exit(SHUTDOWN_EXIT_CODE).

        호출자는 보통 should_shutdown()=True 이후에 호출.
        """
        with self._lock:
            count = self._count
            reason = self._last_reason or "(원인 미상)"
        print(
            f"\n[중단] {label}: 누적 {count}건 실패, "
            f"서버 다운 가능성 있어 종료 (last reason: {reason})",
            file=sys.stderr,
        )
        sys.exit(SHUTDOWN_EXIT_CODE)
