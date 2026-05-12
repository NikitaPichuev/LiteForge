"""
Send zkCodex GM on Arc Testnet.
"""
from __future__ import annotations

import argparse
import logging
import pathlib
import sys
from datetime import datetime

from eth_account import Account
from web3 import Web3

from key_utils import read_private_key as read_selected_private_key


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
KEYS_FILE = PROJECT_ROOT / "keys.txt"

ARC_CHAIN_ID = 5042002
ARC_RPC = "https://rpc.testnet.arc.network"
ARC_RPCS = [
    "https://rpc.testnet.arc.network",
    "https://rpc.quicknode.testnet.arc.network",
    "https://rpc.blockdaemon.testnet.arc.network",
    "https://rpc.drpc.testnet.arc.network",
]
GM_CONTRACT = Web3.to_checksum_address("0x1290B4f2a419A316467b580a088453a233e9ADCc")

GM_ABI = [
    {
        "type": "function",
        "name": "gmFee",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "timeLimit",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "lastGm",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "currentStreak",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "totalGMs",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "sayGM",
        "stateMutability": "payable",
        "inputs": [{"name": "message", "type": "string"}],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "sayGMTo",
        "stateMutability": "payable",
        "inputs": [
            {"name": "recipient", "type": "address"},
            {"name": "message", "type": "string"},
        ],
        "outputs": [],
    },
]


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"arc_gm_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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
    parser = argparse.ArgumentParser(description="Send zkCodex GM on Arc Testnet")
    parser.add_argument("--message", default="GM!", help="custom GM message")
    parser.add_argument("--recipient", default=None, help="optional recipient; own wallet if omitted")
    parser.add_argument("--send", action="store_true", help="required: send real transaction")
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
    for rpc_url in ARC_RPCS:
        send_w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        try:
            tx_hash = send_w3.eth.send_raw_transaction(raw_tx)
            if rpc_url != ARC_RPC:
                log.info("Sent through fallback RPC: %s", rpc_url)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("RPC send failed on %s: %s", rpc_url, exc)
    if tx_hash is None or send_w3 is None:
        raise RuntimeError(f"All RPC sends failed: {last_error}")

    log.info("GM tx sent: %s", tx_hash.hex())
    receipt = send_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    log.info("Receipt status: %s", receipt.status)
    log.info("Block: %s", receipt.blockNumber)
    log.info("Gas used: %s", receipt.gasUsed)
    if receipt.status != 1:
        raise RuntimeError(f"GM reverted: {tx_hash.hex()}")
    return tx_hash.hex(), receipt


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("arc_gm")

    if not args.send:
        log.error("This script is for real GM sends. Add --send.")
        log.info("Log saved to: %s", log_file)
        return 1

    pk = read_private_key()
    account = Account.from_key(pk)

    w3 = Web3(Web3.HTTPProvider(ARC_RPC, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        log.error("Cannot connect to Arc RPC: %s", ARC_RPC)
        log.info("Log saved to: %s", log_file)
        return 1
    if w3.eth.chain_id != ARC_CHAIN_ID:
        log.error("Wrong chain id: got %s, expected %s", w3.eth.chain_id, ARC_CHAIN_ID)
        log.info("Log saved to: %s", log_file)
        return 1

    contract = w3.eth.contract(address=GM_CONTRACT, abi=GM_ABI)
    recipient = Web3.to_checksum_address(args.recipient) if args.recipient else account.address
    message = args.message.strip() or "GM!"

    gm_fee = contract.functions.gmFee().call()
    time_limit = contract.functions.timeLimit().call()
    last_gm = contract.functions.lastGm(account.address).call()
    current_streak = contract.functions.currentStreak(account.address).call()
    total_gms_before = contract.functions.totalGMs(account.address).call()
    now_ts = int(datetime.now().timestamp())

    log.info("Wallet: %s", account.address)
    log.info("Recipient: %s", recipient)
    log.info("Message: %s", message)
    log.info("GM contract: %s", GM_CONTRACT)
    log.info("GM fee wei: %s", gm_fee)
    log.info("Time limit seconds: %s", time_limit)
    log.info("Current streak before: %s", current_streak)
    log.info("Total GMs before: %s", total_gms_before)
    log.info("Last GM timestamp: %s", last_gm)
    if last_gm:
        next_gm_ts = last_gm + time_limit
        remaining = max(0, next_gm_ts - now_ts)
        log.info("Seconds until next allowed GM: %s", remaining)

    if last_gm and now_ts < last_gm + time_limit:
        log.error("Too early for next GM. Wait %s more seconds.", (last_gm + time_limit) - now_ts)
        log.info("Log saved to: %s", log_file)
        return 1

    nonce = w3.eth.get_transaction_count(account.address, "pending")
    fn = contract.functions.sayGM(message) if recipient == account.address else contract.functions.sayGMTo(recipient, message)
    method_name = "sayGM" if recipient == account.address else "sayGMTo"

    tx = fn.build_transaction(
        {
            "from": account.address,
            "chainId": ARC_CHAIN_ID,
            "nonce": nonce,
            "value": gm_fee,
        }
    )
    gas = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas * 1.2)
    tx = build_fee_fields(w3, tx)

    log.info("Method: %s", method_name)
    log.info("Estimated gas: %s", gas)
    log.info("Gas limit used: %s", tx["gas"])
    log.info("Max fee per gas wei: %s", tx["maxFeePerGas"])
    log.info("Max priority fee per gas wei: %s", tx["maxPriorityFeePerGas"])

    tx_hash, _ = sign_and_send(account, tx, log)

    total_gms_after = contract.functions.totalGMs(account.address).call()
    current_streak_after = contract.functions.currentStreak(account.address).call()
    log.info("Total GMs after: %s", total_gms_after)
    log.info("Current streak after: %s", current_streak_after)
    log.info("Explorer: https://testnet.arcscan.app/tx/%s", tx_hash)
    log.info("Log saved to: %s", log_file)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        logging.exception("Fatal error: %s", exc)
        sys.exit(1)
