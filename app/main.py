"""
LitVM LiteForge bot - single-wallet automation of on-chain actions.

Usage:
    pip install -r requirements.txt
    python app\main.py

Before first run, fill in contract addresses in config.py.
"""
import argparse
import logging
import pathlib
import sys
from datetime import datetime

import config
from checks import print_report, run_checks
from client import Tx, load_account, make_web3
import mod_ayni
import mod_lester
import mod_liteswap
import mod_omni
import mod_omni_create


def setup_logging():
    project_root = pathlib.Path(__file__).resolve().parent.parent
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-7s  %(name)-12s  %(message)s",
        datefmt="%H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    logging.getLogger("main").info("Log file: %s", log_file)
    return log_file


def parse_args():
    parser = argparse.ArgumentParser(description="LitVM LiteForge bot")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="run diagnostics and exit without connecting to RPC or sending transactions",
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="skip strict config checks before run",
    )
    return parser.parse_args()


def safe(name, fn, *args, **kwargs):
    log = logging.getLogger("main")
    try:
        fn(*args, **kwargs)
    except Exception as e:
        log.exception("[%s] failed: %s", name, e)


def main():
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("main")

    report = run_checks(strict_config=not args.skip_checks)
    print_report(report)
    for item in report.errors:
        log.error("[check] %s", item)
    for item in report.warnings:
        log.warning("[check] %s", item)

    if args.check_only:
        return 0 if report.ok else 1
    if not report.ok:
        log.error("Fix the errors above, then run again. Log saved to: %s", log_file)
        return 1

    try:
        w3 = make_web3()
        acct = load_account()
        tx = Tx(w3, acct)
    except Exception as e:
        log.exception("Startup failed before transactions: %s", e)
        log.error("Log saved to: %s", log_file)
        return 1

    bal = w3.eth.get_balance(acct.address)
    log.info("zkLTC balance: %s", w3.from_wei(bal, "ether"))
    if bal == 0:
        log.error("No zkLTC. Request from https://liteforge.hub.caldera.xyz/ manually.")
        log.error("Log saved to: %s", log_file)
        return 1

    safe("liteswap", mod_liteswap.run, w3, tx)

    omni_target = getattr(config, "OMNI_TARGET_TOKEN", "0x" + "0" * 40)
    if omni_target != "0x" + "0" * 40:
        safe("omni-swap", mod_omni.run, w3, tx, omni_target)
    else:
        log.warning("OMNI_TARGET_TOKEN not set - skipping omni swap")

    safe("lester", mod_lester.run, w3, tx)
    safe("omni-create", mod_omni_create.run, w3, tx)
    safe("ayni", mod_ayni.run, w3, tx)

    log.info("done. Log saved to: %s", log_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
