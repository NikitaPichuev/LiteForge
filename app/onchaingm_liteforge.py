"""
Run OnChainGM actions on LitVM LiteForge.
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
from decimal import Decimal

from eth_account import Account
from web3 import Web3

from key_utils import read_private_key as read_selected_private_key


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"

LITEFORGE_CHAIN_ID = 4441
LITEFORGE_RPCS = [
    "https://liteforge.rpc.caldera.xyz/http",
    "https://liteforge.rpc.caldera.xyz/infra-partner-http",
]
LITEFORGE_EXPLORER = "https://liteforge.explorer.caldera.xyz"

ZERO_ADDRESS = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
DEFAULT_REFERRER = ZERO_ADDRESS
GM_CONTRACT = Web3.to_checksum_address("0xA0692f67ffcEd633f9c5CfAefd83FC4F21973D01")
DEPLOY_FACTORY = Web3.to_checksum_address("0x59c27c39A126a9B5eCADdd460C230C857e1Deb35")
DEPLOY_FEE_WEI = int(Decimal("0.01") * Decimal(10) ** 18)
NONCE_HINT_RE = re.compile(r"(?:state|next nonce)\s*[: ]\s*(\d+)", re.IGNORECASE)

GM_ABI = [
    {
        "type": "function",
        "name": "GM_FEE",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "timeUntilNextGM",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "onChainGM",
        "stateMutability": "payable",
        "inputs": [{"name": "referrer", "type": "address"}],
        "outputs": [],
    },
]

DEPLOY_ABI = [
    {
        "type": "function",
        "name": "deploy",
        "stateMutability": "payable",
        "inputs": [],
        "outputs": [],
    },
    {
        "type": "event",
        "name": "ContractDeployed",
        "anonymous": False,
        "inputs": [
            {"indexed": False, "name": "contractAddress", "type": "address"},
            {"indexed": False, "name": "owner", "type": "address"},
        ],
    },
]


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"onchaingm_liteforge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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
    parser = argparse.ArgumentParser(description="Run OnChainGM LiteForge GM + deploy")
    parser.add_argument("--referrer", default=DEFAULT_REFERRER, help="referrer address, zero/self is ignored")
    parser.add_argument("--send", action="store_true", help="required: send real transactions")
    return parser.parse_args()


def short_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc).replace(chr(10), ' ')[:180]}"


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


def build_and_send(w3: Web3, account, nonce: int, log: logging.Logger, label: str, contract_fn, value: int):
    balance = w3.eth.get_balance(account.address)
    if balance < value:
        raise RuntimeError(f"{label}: not enough zkLTC for value, need {value}, have {balance}")

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
    log = logging.getLogger("onchaingm_liteforge")

    if not args.send:
        log.error("This script is for real OnChainGM transactions. Add --send.")
        log.info("Log saved to: %s", log_file)
        return 1

    account = Account.from_key(read_selected_private_key())
    referrer = Web3.to_checksum_address(args.referrer) if args.referrer else ZERO_ADDRESS
    if referrer.lower() == account.address.lower():
        referrer = ZERO_ADDRESS

    w3 = connect_rpc(log)
    gm_contract = w3.eth.contract(address=GM_CONTRACT, abi=GM_ABI)
    deploy_contract = w3.eth.contract(address=DEPLOY_FACTORY, abi=DEPLOY_ABI)

    gm_fee = gm_contract.functions.GM_FEE().call()
    time_until_next = gm_contract.functions.timeUntilNextGM(account.address).call()

    log.info("Wallet: %s", account.address)
    log.info("Referrer used: %s", referrer)
    log.info("GM contract: %s", GM_CONTRACT)
    log.info("Deploy factory: %s", DEPLOY_FACTORY)
    log.info("GM fee wei: %s", gm_fee)
    log.info("Deploy fee wei: %s", DEPLOY_FEE_WEI)
    log.info("Seconds until next GM: %s", time_until_next)

    nonce = get_safe_pending_nonce(account.address)
    results: list[str] = []

    if int(time_until_next) > 0:
        log.info("GM skipped: cooldown active, remaining %s seconds", time_until_next)
        results.append("GM SKIPPED: cooldown")
    else:
        try:
            nonce, gm_hash, _ = build_and_send(
                w3,
                account,
                nonce,
                log,
                "OnChainGM GM",
                gm_contract.functions.onChainGM(referrer),
                gm_fee,
            )
            results.append(f"GM OK: {gm_hash}")
        except Exception as exc:  # noqa: BLE001
            log.warning("GM failed, deploy will still run: %s", short_error(exc))
            results.append(f"GM FAILED: {short_error(exc)}")

    time.sleep(2 + random.random() * 3)

    try:
        _, deploy_hash, receipt = build_and_send(
            w3,
            account,
            nonce,
            log,
            "OnChainGM Deploy",
            deploy_contract.functions.deploy(),
            DEPLOY_FEE_WEI,
        )
        results.append(f"Deploy OK: {deploy_hash}")
        try:
            events = deploy_contract.events.ContractDeployed().process_receipt(receipt)
            if events:
                deployed = events[0]["args"]["contractAddress"]
                log.info("Deployed contract: %s", deployed)
                log.info("Deployed contract explorer: %s/address/%s", LITEFORGE_EXPLORER, deployed)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not decode deployed contract event: %s", exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("Deploy failed: %s", short_error(exc))
        results.append(f"Deploy FAILED: {short_error(exc)}")

    for result in results:
        log.info("Result: %s", result)
    log.info("Log saved to: %s", log_file)
    return 0 if any("OK:" in item for item in results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        logging.exception("Fatal error: %s", exc)
        sys.exit(1)
