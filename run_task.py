"""모든 task의 단일 진입점.

Usage:
    python -m run_task <dag> <task_id>
    
Example:
    python -m run_task parse load_pipeline_state
"""
import sys
import importlib


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: run_task.py <dag> <task_id>", file=sys.stderr)
        return 2
    
    dag_name, task_id = sys.argv[1], sys.argv[2]
    module_path = f"{dag_name}.{task_id}"
    
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        print(f"Task module not found: {module_path}", file=sys.stderr)
        print(f"  detail: {e}", file=sys.stderr)
        return 2
    
    if not hasattr(module, "run"):
        print(f"{module_path} must define run()", file=sys.stderr)
        return 2

    # task가 표준 argparse를 쓸 수 있도록 sys.argv를 task 기준으로 재구성
    sys.argv = [module_path] + sys.argv[3:]
    module.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
