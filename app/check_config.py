"""
Standalone diagnostics entry point.
Run with:
    python check_config.py
"""
import sys

from checks import print_report, run_checks


def main() -> int:
    report = run_checks(strict_config=True)
    print_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
