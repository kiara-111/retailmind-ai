"""Run by GitHub Actions every 30 minutes: sends every automation that is due."""
import sys

from core import engine, store


def main() -> int:
    due = store.due_subscriptions()
    print(f"Storage: {store.backend()} | due automations: {len(due)}")
    failed = 0
    for sub in due:
        result = engine.run(sub, trigger="schedule")
        print(f"- {sub['format']} via {sub['channel']} -> {result['status']}: {result['detail']}")
        failed += result["status"] != "sent"
    return 1 if due and failed == len(due) else 0


if __name__ == "__main__":
    sys.exit(main())
