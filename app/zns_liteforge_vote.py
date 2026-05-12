"""
Real ZNS LiteForge vote sender.
"""
from __future__ import annotations

import argparse
import logging
import pathlib
import random
import sys
import time
from datetime import datetime

from eth_account import Account
from web3 import Web3

from key_utils import read_private_key as read_selected_private_key


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
KEYS_FILE = PROJECT_ROOT / "keys.txt"

LITEFORGE_CHAIN_ID = 4441
LITEFORGE_RPC = "https://liteforge.rpc.caldera.xyz/http"
LITEFORGE_RPCS = [
    "https://liteforge.rpc.caldera.xyz/http",
    "https://liteforge.rpc.caldera.xyz/infra-partner-http",
]

VOTE_CONTRACT = Web3.to_checksum_address("0x3e048310c04461d932B92085c89d23909BFb40c4")
ZERO_ADDRESS = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")

VOTE_ABI = [
    {
        "type": "function",
        "name": "vote",
        "stateMutability": "payable",
        "inputs": [{"name": "referral", "type": "address"}],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "fee",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "getTotalVotes",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "getUserVotes",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
]


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"zns_liteforge_vote_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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


def read_private_key() -> str:
    return read_selected_private_key()


def parse_args():
    parser = argparse.ArgumentParser(description="Send ZNS LiteForge vote")
    parser.add_argument("--count", type=int, default=1, help="number of real votes")
    parser.add_argument("--send", action="store_true", help="required: send real transactions")
    return parser.parse_args()


def build_fee_fields(w3: Web3, tx: dict) -> dict:
    tx.pop("gasPrice", None)
    tx["maxFeePerGas"] = w3.eth.gas_price
    tx["maxPriorityFeePerGas"] = 0
    return tx


def sign_and_send(account, tx: dict, log: logging.Logger):
    signed = account.sign_transaction(tx)
    raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")

    last_error = None
    tx_hash = None
    send_w3 = None
    for rpc_url in LITEFORGE_RPCS:
        send_w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        try:
            tx_hash = send_w3.eth.send_raw_transaction(raw_tx)
            if rpc_url != LITEFORGE_RPC:
                log.info("Sent through fallback RPC: %s", rpc_url)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("RPC send failed on %s: %s", rpc_url, exc)
    if tx_hash is None or send_w3 is None:
        raise RuntimeError(f"All RPC sends failed: {last_error}")

    log.info("Vote tx sent: %s", tx_hash.hex())
    receipt = send_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    log.info("Receipt status: %s", receipt.status)
    log.info("Block: %s", receipt.blockNumber)
    log.info("Gas used: %s", receipt.gasUsed)
    if receipt.status != 1:
        raise RuntimeError(f"Vote reverted: {tx_hash.hex()}")
    return tx_hash.hex(), receipt


def sleep_between_actions(log: logging.Logger) -> None:
    delay = random.uniform(2, 5)
    log.info("Pause between actions: %.1fs", delay)
    time.sleep(delay)


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("zns_vote")

    if not args.send:
        log.error("This script is for real votes. Add --send.")
        log.info("Log saved to: %s", log_file)
        return 1
    if args.count < 1 or args.count > 20:
        log.error("Vote count must be in range 1..20. Got: %s", args.count)
        log.info("Log saved to: %s", log_file)
        return 1

    pk = read_private_key()
    account = Account.from_key(pk)

    w3 = Web3(Web3.HTTPProvider(LITEFORGE_RPC, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        log.error("Cannot connect to LiteForge RPC: %s", LITEFORGE_RPC)
        log.info("Log saved to: %s", log_file)
        return 1
    if w3.eth.chain_id != LITEFORGE_CHAIN_ID:
        log.error("Wrong chain id: got %s, expected %s", w3.eth.chain_id, LITEFORGE_CHAIN_ID)
        log.info("Log saved to: %s", log_file)
        return 1

    contract = w3.eth.contract(address=VOTE_CONTRACT, abi=VOTE_ABI)
    fee = contract.functions.fee().call()
    user_votes_before = contract.functions.getUserVotes(account.address).call()
    total_votes_before = contract.functions.getTotalVotes().call()
    balance = w3.eth.get_balance(account.address)

    log.info("Wallet: %s", account.address)
    log.info("Vote contract: %s", VOTE_CONTRACT)
    log.info("Referral used: %s", ZERO_ADDRESS)
    log.info("Count: %s", args.count)
    log.info("Vote fee wei: %s", fee)
    log.info("User votes before: %s", user_votes_before)
    log.info("Total votes before: %s", total_votes_before)
    log.info("LiteForge balance wei: %s", balance)

    nonce = w3.eth.get_transaction_count(account.address, "pending")

    for step in range(1, args.count + 1):
        tx = contract.functions.vote(ZERO_ADDRESS).build_transaction(
            {
                "from": account.address,
                "chainId": LITEFORGE_CHAIN_ID,
                "nonce": nonce,
                "value": fee,
            }
        )
        gas = w3.eth.estimate_gas(tx)
        tx["gas"] = int(gas * 1.2)
        tx = build_fee_fields(w3, tx)

        total_required = tx["value"] + tx["gas"] * tx["maxFeePerGas"]
        current_balance = w3.eth.get_balance(account.address)
        if current_balance < total_required:
            raise RuntimeError(
                f"Not enough zkLTC for vote {step}: need {total_required}, have {current_balance}"
            )

        log.info("Vote %s/%s estimated gas: %s", step, args.count, gas)
        log.info("Vote %s/%s gas limit used: %s", step, args.count, tx["gas"])
        log.info("Vote %s/%s max fee per gas wei: %s", step, args.count, tx["maxFeePerGas"])
        log.info("Vote %s/%s max priority fee per gas wei: %s", step, args.count, tx["maxPriorityFeePerGas"])
        tx_hash, _ = sign_and_send(account, tx, log)
        log.info("Explorer: https://liteforge.explorer.caldera.xyz/tx/%s", tx_hash)
        nonce += 1
        if step < args.count:
            sleep_between_actions(log)

    user_votes_after = contract.functions.getUserVotes(account.address).call()
    total_votes_after = contract.functions.getTotalVotes().call()
    log.info("User votes after: %s", user_votes_after)
    log.info("Total votes after: %s", total_votes_after)
    log.info("Log saved to: %s", log_file)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        logging.exception("Fatal error: %s", exc)
        sys.exit(1)
