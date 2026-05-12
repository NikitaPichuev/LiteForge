"""
Browser-only Circle faucet flow for Arc Testnet.

This script opens the public Circle faucet page in Chrome, fills the address,
then waits until the user manually completes reCAPTCHA and clicks the request button.
After a successful result (or a handled failure), it moves to the next address.
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import random
import sys
import time
from datetime import datetime

from eth_account import Account
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from web3 import Web3

from key_utils import read_key_lines


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
KEYS_FILE = PROJECT_ROOT / "keys.txt"
ADDRESSES_FILE = PROJECT_ROOT / "wallet_addresses.txt"
LEGACY_ADDRESSES_FILE = PROJECT_ROOT / "faucet_addresses.txt"

FAUCET_PAGE_URL = "https://faucet.circle.com/?allow=true"
GRAPHQL_URL = "https://faucet.circle.com/api/graphql"
REQUEST_FORM_SELECTOR = '[data-testid="request-token-form"]'
ADDRESS_INPUT_SELECTOR = 'input[name="address"]'
SUCCESS_BUTTON_TEXT = "Get more tokens"
SUCCESS_TITLE_TEXT = "Tokens sent"
DEFAULT_TIMEOUT_MINUTES = 20
FORM_STABILIZE_MS = 5000


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"circle_faucet_arc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    fmt = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    return log_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Circle faucet browser-only flow")
    parser.add_argument("--pause-min", type=int, default=7)
    parser.add_argument("--pause-max", type=int, default=20)
    parser.add_argument("--timeout-minutes", type=int, default=DEFAULT_TIMEOUT_MINUTES)
    return parser.parse_args()


def derive_addresses_from_keys() -> list[str]:
    addresses: list[str] = []
    for private_key in read_key_lines(KEYS_FILE):
        addresses.append(Account.from_key(private_key).address)
    return addresses


def save_addresses_file(addresses: list[str]) -> None:
    content = "\n".join(addresses) + "\n"
    ADDRESSES_FILE.write_text(content, encoding="utf-8")


def read_addresses_from_file(path: pathlib.Path) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not Web3.is_address(line):
            raise RuntimeError(f"Invalid address in {path.name}: {line}")
        out.append(Web3.to_checksum_address(line))
    return out


def load_target_addresses(log: logging.Logger) -> tuple[list[str], str]:
    wallet_addresses = read_addresses_from_file(ADDRESSES_FILE)
    if wallet_addresses:
        return wallet_addresses, ADDRESSES_FILE.name

    legacy_addresses = read_addresses_from_file(LEGACY_ADDRESSES_FILE)
    if legacy_addresses:
        save_addresses_file(legacy_addresses)
        log.warning(
            "%s found and copied to %s. Use %s from now on.",
            LEGACY_ADDRESSES_FILE.name,
            ADDRESSES_FILE.name,
            ADDRESSES_FILE.name,
        )
        return legacy_addresses, LEGACY_ADDRESSES_FILE.name

    derived = derive_addresses_from_keys()
    save_addresses_file(derived)
    log.warning(
        "%s was missing or empty. Created it from %s with %d addresses.",
        ADDRESSES_FILE.name,
        KEYS_FILE.name,
        len(derived),
    )
    return derived, KEYS_FILE.name


def open_faucet_form(page) -> None:
    page.goto(FAUCET_PAGE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector(REQUEST_FORM_SELECTOR, timeout=60000)
    # Circle faucet hydrates the form after the first paint and can wipe early input.
    page.wait_for_timeout(FORM_STABILIZE_MS)


def fill_address(page, address: str) -> None:
    field = page.locator(ADDRESS_INPUT_SELECTOR)
    field.wait_for(state="visible", timeout=60000)
    for attempt in range(1, 6):
        field.fill("")
        field.fill(address)
        page.wait_for_timeout(750)
        current = field.input_value().strip()
        if current == address:
            return
    raise RuntimeError(f"Failed to keep address in faucet field: {address}")


def wait_for_request_result(page, timeout_ms: int):
    matched: list = []

    def is_request_token_response(response) -> bool:
        if response.request.method != "POST":
            return False
        if not response.url.startswith(GRAPHQL_URL):
            return False
        post_data = response.request.post_data or ""
        return "requestToken" in post_data

    def on_response(response) -> None:
        try:
            if is_request_token_response(response):
                matched.append(response)
        except Exception:
            return

    page.on("response", on_response)
    started = time.monotonic()
    try:
        while True:
            if matched:
                response = matched[0]
                payload = response.json()
                return response.status, payload
            if (time.monotonic() - started) * 1000 >= timeout_ms:
                raise PlaywrightTimeoutError("Timed out waiting for requestToken response")
            time.sleep(0.25)
    finally:
        page.remove_listener("response", on_response)


def classify_result(payload: dict) -> tuple[str, str]:
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if errors:
        first_error = errors[0] if isinstance(errors, list) and errors else {}
        return "error", first_error.get("message", "unknown GraphQL error")

    request_token = payload.get("data", {}).get("requestToken", {})
    status = request_token.get("status")
    if status == "success":
        return "success", request_token.get("explorerLink", "")
    if status == "rate_limited":
        return "rate_limited", "Circle faucet rate limit hit"
    return "error", f"unexpected request status: {status}"


def run_browser_flow(addresses: list[str], args: argparse.Namespace, log: logging.Logger) -> int:
    timeout_ms = args.timeout_minutes * 60 * 1000

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()

        try:
            total = len(addresses)
            for index, address in enumerate(addresses, start=1):
                log.info("Address %d/%d: %s", index, total, address)
                open_faucet_form(page)
                fill_address(page, address)
                page.bring_to_front()

                log.info(
                    "Manual step required for %s: complete reCAPTCHA and click the faucet button in Chrome. Waiting up to %d minutes.",
                    address,
                    args.timeout_minutes,
                )

                try:
                    http_status, payload = wait_for_request_result(page, timeout_ms)
                except PlaywrightTimeoutError:
                    log.error(
                        "Timed out waiting for faucet submission result for %s after %d minutes.",
                        address,
                        args.timeout_minutes,
                    )
                    return 1

                log.info("HTTP status: %s", http_status)
                log.info("Response JSON: %s", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                result_kind, details = classify_result(payload)

                if result_kind == "success":
                    if details:
                        log.info("Explorer: %s", details)
                    if page.get_by_text(SUCCESS_TITLE_TEXT).count():
                        log.info("Success page detected in browser")
                    elif page.get_by_role("button", name=SUCCESS_BUTTON_TEXT).count():
                        log.info("Success button detected in browser")
                    log.info("Faucet OK for %s", address)
                elif result_kind == "rate_limited":
                    log.warning("Rate limited for %s", address)
                else:
                    log.error("Faucet failed for %s: %s", address, details)

                if index < total:
                    pause_seconds = random.randint(args.pause_min, args.pause_max)
                    log.info("Pause before next address: %ss", pause_seconds)
                    time.sleep(pause_seconds)
        finally:
            context.close()
            browser.close()

    return 0


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("circle_faucet_arc")

    if args.pause_min < 0 or args.pause_max < 0:
        raise RuntimeError("Pause values must be >= 0")
    if args.pause_min > args.pause_max:
        raise RuntimeError("pause-min must be <= pause-max")
    if args.timeout_minutes < 1:
        raise RuntimeError("timeout-minutes must be >= 1")

    addresses, source_name = load_target_addresses(log)
    log.info("Mode: browser-only")
    log.info("Source: %s", source_name)
    log.info("Total addresses: %d", len(addresses))
    log.info("Address file: %s", ADDRESSES_FILE)
    log.info("Page: %s", FAUCET_PAGE_URL)
    exit_code = run_browser_flow(addresses, args, log)
    log.info("Log saved to: %s", log_file)
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        logging.exception("Fatal error: %s", exc)
        sys.exit(1)
