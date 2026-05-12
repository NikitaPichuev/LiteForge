"""
Mint .litevm domains on Infinityname for LitVM LiteForge.
"""
from __future__ import annotations

import argparse
import logging
import pathlib
import random
import re
import sys
import time
from datetime import datetime

from eth_account import Account
from web3 import Web3
from web3.logs import DISCARD

from key_utils import get_active_key_index, read_private_key as read_selected_private_key


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"

LITEFORGE_CHAIN_ID = 4441
LITEFORGE_RPCS = [
    "https://liteforge.rpc.caldera.xyz/http",
    "https://liteforge.rpc.caldera.xyz/infra-partner-http",
]
LITEFORGE_EXPLORER = "https://liteforge.explorer.caldera.xyz"

ZERO_ADDRESS = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
REFERRER = Web3.to_checksum_address("0xF278AC8e97dd418A3ce13307Fa1b44Ff87a18F7c")
INFINITYNAME_CONTRACT = Web3.to_checksum_address("0x76a816EFa69e3183972ff7a231F5C8d7b065d9De")
NONCE_HINT_RE = re.compile(r"(?:state|next nonce)\s*[: ]\s*(\d+)", re.IGNORECASE)
LABEL_RE = re.compile(r"^[a-z0-9-]+$")
RNG = random.SystemRandom()
RANDOM_PARTS = [
    "ka", "zen", "tor", "ly", "vak", "mio", "sor", "nex", "rin", "fal",
    "qu", "dra", "vel", "nor", "pix", "lum", "trix", "vor", "sel", "jin",
    "oro", "kei", "mur", "xan", "vex", "talo", "sai", "bex", "luro", "fyn",
]

INFINITYNAME_ABI = [
    {
        "type": "function",
        "name": "isAvailable",
        "stateMutability": "view",
        "inputs": [{"name": "domain", "type": "string"}],
        "outputs": [{"type": "bool"}],
    },
    {
        "type": "function",
        "name": "getPriceWithReferral",
        "stateMutability": "view",
        "inputs": [{"name": "referrer", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "price",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "suffix",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "string"}],
    },
    {
        "type": "function",
        "name": "register",
        "stateMutability": "payable",
        "inputs": [
            {"name": "domain", "type": "string"},
            {"name": "referrer", "type": "address"},
        ],
        "outputs": [],
    },
    {
        "type": "event",
        "name": "DomainRegistered",
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "owner", "type": "address"},
            {"indexed": False, "name": "domain", "type": "string"},
            {"indexed": False, "name": "tokenId", "type": "uint256"},
        ],
    },
]


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"infinityname_liteforge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    formatter = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    return log_file


def parse_args():
    parser = argparse.ArgumentParser(description="Mint Infinityname .litevm domain on LiteForge")
    parser.add_argument("--base", default="litevm", help="base label, lowercase, used to build unique names")
    parser.add_argument("--send", action="store_true", help="required: send real transaction")
    return parser.parse_args()


def normalize_base_label(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    if not normalized:
        raise RuntimeError("Base name is empty after normalization")
    if not LABEL_RE.fullmatch(normalized):
        raise RuntimeError("Base name must contain only lowercase a-z, 0-9 or hyphen")
    return normalized


def connect_rpc(log: logging.Logger) -> Web3:
    last_error = None
    for rpc in LITEFORGE_RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
            if not w3.is_connected():
                log.warning("RPC not connected: %s", rpc)
                continue
            if w3.eth.chain_id != LITEFORGE_CHAIN_ID:
                log.warning("Wrong chain on %s: %s", rpc, w3.eth.chain_id)
                continue
            log.info("RPC: %s", rpc)
            return w3
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("RPC failed %s: %s", rpc, exc)
    raise RuntimeError(f"Cannot connect to LiteForge RPC: {last_error}")


def build_fee_fields(w3: Web3, tx: dict) -> dict:
    tx.pop("gasPrice", None)
    tx["maxFeePerGas"] = w3.eth.gas_price
    tx["maxPriorityFeePerGas"] = 0
    return tx


def get_safe_pending_nonce(address: str, fallback: int | None = None) -> int:
    best_nonce = -1
    last_error = None
    for rpc in LITEFORGE_RPCS:
        try:
            probe = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
            if not probe.is_connected() or probe.eth.chain_id != LITEFORGE_CHAIN_ID:
                continue
            best_nonce = max(best_nonce, probe.eth.get_transaction_count(address, "pending"))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if best_nonce < 0:
        if fallback is not None:
            return fallback
        raise RuntimeError(f"Cannot fetch pending nonce: {last_error}")
    return best_nonce


def extract_nonce_hint(exc: Exception) -> int | None:
    match = NONCE_HINT_RE.search(str(exc))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def sign_and_send(account, tx: dict, log: logging.Logger, label: str):
    last_error = None
    current_nonce = tx["nonce"]
    for attempt in range(1, 5):
        safe_nonce = get_safe_pending_nonce(account.address, fallback=current_nonce)
        if safe_nonce > current_nonce:
            log.info("%s nonce adjusted: %s -> %s", label, current_nonce, safe_nonce)
            current_nonce = safe_nonce

        send_tx = dict(tx)
        send_tx["nonce"] = current_nonce
        signed = account.sign_transaction(send_tx)
        raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")

        for rpc in LITEFORGE_RPCS:
            try:
                send_w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
                if not send_w3.is_connected() or send_w3.eth.chain_id != LITEFORGE_CHAIN_ID:
                    continue
                tx_hash = send_w3.eth.send_raw_transaction(raw_tx)
                if rpc != LITEFORGE_RPCS[0]:
                    log.info("%s sent through fallback RPC: %s", label, rpc)
                tx_hash_hex = tx_hash.hex()
                log.info("%s tx sent: %s", label, tx_hash_hex)
                receipt = send_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
                log.info("%s receipt status: %s", label, receipt.status)
                log.info("%s block: %s", label, receipt.blockNumber)
                log.info("%s gas used: %s", label, receipt.gasUsed)
                if receipt.status != 1:
                    raise RuntimeError(f"{label} reverted: {tx_hash_hex}")
                log.info("%s explorer: %s/tx/%s", label, LITEFORGE_EXPLORER, tx_hash_hex)
                return tx_hash_hex, receipt
            except ValueError as exc:
                last_error = exc
                if "nonce too low" in str(exc).lower():
                    hinted_nonce = extract_nonce_hint(exc)
                    current_nonce = max(current_nonce + 1, hinted_nonce or current_nonce + 1)
                    log.warning("%s nonce too low, retry %s with nonce %s: %s", label, attempt, current_nonce, exc)
                    break
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                log.warning("%s RPC send failed on %s: %s", label, rpc, exc)
        time.sleep(1)
    raise RuntimeError(f"{label}: all sends failed: {last_error}")


def random_fragment(min_parts: int = 2, max_parts: int = 4, digit_count: int = 0) -> str:
    count = RNG.randint(min_parts, max_parts)
    text = "".join(RNG.choice(RANDOM_PARTS) for _ in range(count))
    if digit_count > 0:
        text += "".join(str(RNG.randint(0, 9)) for _ in range(digit_count))
    return text


def randomize_base(base: str) -> str:
    _ = base
    return f"{random_fragment(2, 4, RNG.randint(1, 2))}"


def make_candidates(base: str, address: str, key_index: int) -> list[str]:
    addr4 = address[-4:].lower()
    addr6 = address[-6:].lower()
    raw_candidates = [randomize_base(base) for _ in range(18)] + [
        f"{random_fragment(2, 4, 2)}",
        f"{random_fragment(1, 2, 0)}{random_fragment(1, 2, 2)}",
        f"{random_fragment(2, 3, 0)}{addr4}",
        f"{random_fragment(2, 3, 0)}{addr6}",
        f"{random_fragment(1, 2, 0)}{key_index}{addr4}",
    ]
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_candidates:
        if not item:
            continue
        item = re.sub(r"-{2,}", "-", item).strip("-")
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def choose_domain_label(contract, base: str, address: str, key_index: int, log: logging.Logger) -> str:
    for candidate in make_candidates(base, address, key_index):
        try:
            available = contract.functions.isAvailable(candidate).call()
        except Exception as exc:  # noqa: BLE001
            log.warning("Availability check failed for %s: %s", candidate, exc)
            continue
        log.info("Candidate %s available: %s", candidate, available)
        if available:
            return candidate
    raise RuntimeError("No free Infinityname candidate found for this wallet")


def build_and_send(w3: Web3, account, nonce: int, log: logging.Logger, label: str, contract_fn, value: int):
    tx = contract_fn.build_transaction(
        {
            "from": account.address,
            "chainId": LITEFORGE_CHAIN_ID,
            "nonce": nonce,
            "value": value,
            "gas": 1,
        }
    )
    tx.pop("gas", None)
    gas = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas * 1.25)
    tx = build_fee_fields(w3, tx)

    total_required = tx["value"] + tx["gas"] * tx["maxFeePerGas"]
    balance = w3.eth.get_balance(account.address)
    if balance < total_required:
        raise RuntimeError(f"{label}: not enough zkLTC, need {total_required}, have {balance}")

    log.info("%s estimated gas: %s", label, gas)
    log.info("%s gas limit used: %s", label, tx["gas"])
    log.info("%s max fee per gas wei: %s", label, tx["maxFeePerGas"])
    log.info("%s max priority fee per gas wei: %s", label, tx["maxPriorityFeePerGas"])
    log.info("%s native value wei: %s", label, tx["value"])

    tx_hash, receipt = sign_and_send(account, tx, log, label)
    return nonce + 1, tx_hash, receipt


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("infinityname_liteforge")

    if not args.send:
        log.error("This script is for real Infinityname transactions. Add --send.")
        log.info("Log saved to: %s", log_file)
        return 1

    base = normalize_base_label(args.base)
    key_index = get_active_key_index()
    account = Account.from_key(read_selected_private_key())
    referrer = ZERO_ADDRESS if account.address.lower() == REFERRER.lower() else REFERRER

    try:
        w3 = connect_rpc(log)
        contract = w3.eth.contract(address=INFINITYNAME_CONTRACT, abi=INFINITYNAME_ABI)

        suffix = contract.functions.suffix().call()
        base_price = contract.functions.price().call()
        referral_price = contract.functions.getPriceWithReferral(referrer).call()
        nonce = get_safe_pending_nonce(account.address)

        log.info("Wallet: %s", account.address)
        log.info("Infinityname contract: %s", INFINITYNAME_CONTRACT)
        log.info("Referral used: %s", referrer)
        log.info("Base label: %s", base)
        log.info("Suffix: %s", suffix)
        log.info("Base price wei: %s", base_price)
        log.info("Referral price wei: %s", referral_price)

        label = choose_domain_label(contract, base, account.address, key_index, log)
        full_domain = f"{label}{suffix}"
        log.info("Selected label: %s", label)
        log.info("Selected domain: %s", full_domain)

        _, tx_hash, receipt = build_and_send(
            w3,
            account,
            nonce,
            log,
            "Infinityname register",
            contract.functions.register(label, referrer),
            referral_price,
        )

        try:
            events = contract.events.DomainRegistered().process_receipt(receipt, errors=DISCARD)
            if events:
                event = events[0]["args"]
                log.info("Registered domain: %s", event.get("domain", full_domain))
                log.info("Registered token id: %s", event.get("tokenId"))
        except Exception as exc:  # noqa: BLE001
            log.warning("DomainRegistered event parse failed: %s", exc)

        log.info("Result: OK: %s", tx_hash)
        log.info("Log saved to: %s", log_file)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("Fatal error: %s", exc, exc_info=True)
        log.info("Log saved to: %s", log_file)
        return 1


if __name__ == "__main__":
    sys.exit(main())
