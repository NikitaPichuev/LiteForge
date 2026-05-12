from __future__ import annotations

import argparse
import os
import pathlib
import random
import re
import subprocess
import sys
import time
from decimal import Decimal

from key_utils import read_key_lines


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
RANGE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)\s*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a command sequentially for every private key in keys.txt"
    )
    parser.add_argument("--pause-min", type=int, default=5)
    parser.add_argument("--pause-max", type=int, default=15)
    parser.add_argument(
        "--stop-on-exit-code",
        type=int,
        action="append",
        default=[],
        help="stop processing remaining wallets if child exits with this code",
    )
    parser.add_argument(
        "--success-if-any",
        action="store_true",
        help="return 0 if at least one wallet command exits successfully",
    )
    parser.add_argument(
        "--status-file",
        help="write run summary as key=value lines",
    )
    parser.add_argument("separator", nargs="?", help="use -- before command")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.pause_min < 0 or args.pause_max < 0:
        parser.error("pause values must be >= 0")
    if args.pause_min > args.pause_max:
        parser.error("pause-min must be <= pause-max")
    if args.separator == "--":
        pass
    elif args.separator:
        args.command = [args.separator] + args.command
    if not args.command:
        parser.error("no command provided")
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("no command provided after --")
    return args


def _decimal_places(value: str) -> int:
    normalized = value.replace(",", ".")
    if "." not in normalized:
        return 0
    return len(normalized.split(".", 1)[1])


def resolve_range_token(token: str) -> str:
    match = RANGE_RE.fullmatch(token)
    if not match:
        return token

    left_raw, right_raw = match.groups()
    left = Decimal(left_raw.replace(",", "."))
    right = Decimal(right_raw.replace(",", "."))
    if left > right:
        raise SystemExit(f"invalid range: {token} (left must be <= right)")

    if left == right:
        return format(left.normalize(), "f").rstrip("0").rstrip(".") or "0"

    scale = max(_decimal_places(left_raw), _decimal_places(right_raw))
    factor = Decimal(10) ** scale
    start = int(left * factor)
    end = int(right * factor)
    picked = Decimal(random.randint(start, end)) / factor

    if scale == 0:
        return str(int(picked))
    return f"{picked:.{scale}f}".rstrip("0").rstrip(".")


def main() -> int:
    args = parse_args()
    keys = read_key_lines()
    total = len(keys)
    overall_exit_code = 0
    success_count = 0
    failure_count = 0
    completed_count = 0
    stop_codes = set(args.stop_on_exit_code)

    for index in range(1, total + 1):
        print(f"[wallet {index}/{total}] start", flush=True)
        env = os.environ.copy()
        env["KEY_INDEX"] = str(index)
        resolved_command = [resolve_range_token(token) for token in args.command]
        randomized_pairs = [
            (original, resolved)
            for original, resolved in zip(args.command, resolved_command)
            if original != resolved
        ]
        if randomized_pairs:
            changes = ", ".join(f"{src} -> {dst}" for src, dst in randomized_pairs)
            print(f"[wallet {index}/{total}] randomized: {changes}", flush=True)
        result = subprocess.run(resolved_command, cwd=PROJECT_ROOT, env=env)
        completed_count += 1
        if result.returncode != 0:
            print(f"[wallet {index}/{total}] failed with exit code {result.returncode}", flush=True)
            overall_exit_code = result.returncode
            failure_count += 1
            if result.returncode in stop_codes:
                print(
                    f"[wallet {index}/{total}] stop requested for exit code {result.returncode}",
                    flush=True,
                )
                break
        else:
            print(f"[wallet {index}/{total}] done", flush=True)
            success_count += 1

        if index < total:
            pause_seconds = random.randint(args.pause_min, args.pause_max)
            print(
                f"[wallet {index}/{total}] pause before next wallet: {pause_seconds}s",
                flush=True,
            )
            time.sleep(pause_seconds)

    if args.status_file:
        status_path = pathlib.Path(args.status_file)
        if not status_path.is_absolute():
            status_path = PROJECT_ROOT / status_path
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(
            "\n".join(
                [
                    f"total={total}",
                    f"completed_count={completed_count}",
                    f"success_count={success_count}",
                    f"failure_count={failure_count}",
                    f"last_exit_code={overall_exit_code}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    if args.success_if_any and success_count > 0:
        return 0
    return overall_exit_code


if __name__ == "__main__":
    sys.exit(main())
