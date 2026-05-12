"""
Bridge native zkLTC from LiteForge to Sepolia through the Arbitrum Nitro native bridge.

This sends a real L2 withdrawal transaction by calling ArbSys.withdrawEth(address)
on LiteForge. Finalization on Sepolia is a separate bridge/outbox process and can
take time, as shown by the Caldera hub UI.
"""
from __future__ import annotations

import argparse
import logging
import pathlib
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractLogicError

from key_utils import read_private_key as read_selected_private_key


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
KEYS_FILE = PROJECT_ROOT / "keys.txt"

LITEFORGE_CHAIN_ID = 4441
LITEFORGE_RPCS = [
    "https://liteforge.rpc.caldera.xyz/http",
    "https://liteforge.rpc.caldera.xyz/infra-partner-http",
]
ARBSYS = Web3.to_checksum_address("0x0000000000000000000000000000000000000064")
NONCE_HINT_RE = re.compile(r"(?:state|next nonce)\s*[: ]\s*(\d+)", re.IGNORECASE)


ARBSYS_ABI = [
    {
        "type": "function",
        "name": "withdrawEth",
        "stateMutability": "payable",
        "inputs": [{"name": "destination", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    }
]


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"liteforge_bridge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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


def parse_decimal(value: str, name: str) -> Decimal:
    normalized = value.strip().replace(",", ".")
    try:
        parsed = Decimal(normalized)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"{name} must be a number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"{name} must be greater than zero")
    return parsed


def parse_args():
    parser = argparse.ArgumentParser(description="Bridge native zkLTC from LiteForge to Sepolia")
    parser.add_argument("--amount", required=True, type=lambda v: parse_decimal(v, "amount"), help="zkLTC amount")
    parser.add_argument("--recipient", default=None, help="Sepolia recipient address, default: own wallet")
    parser.add_argument("--send", action="store_true", help="required: send real transaction")
    return parser.parse_args()


def connect_rpc(log: logging.Logger) -> Web3:
    last_error = None
    for rpc in LITEFORGE_RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
            if not w3.is_connected():
                log.warning("RPC not connected: %s", rpc)
                continue
            chain_id = w3.eth.chain_id
            if chain_id != LITEFORGE_CHAIN_ID:
                log.warning("Wrong chain on %s: got %s", rpc, chain_id)
                continue
            log.info("RPC: %s", rpc)
            return w3
        except Exception as exc:
            last_error = exc
            log.warning("RPC failed %s: %s", rpc, exc)
    raise RuntimeError(f"Cannot connect to LiteForge RPC: {last_error}")


def build_fee_fields(w3: Web3, tx: dict) -> dict:
    if "maxFeePerGas" in tx or "maxPriorityFeePerGas" in tx:
        tx.pop("gasPrice", None)
        tx.setdefault("maxFeePerGas", w3.eth.gas_price)
        tx.setdefault("maxPriorityFeePerGas", 0)
    else:
        tx["gasPrice"] = w3.eth.gas_price
    return tx


def get_safe_pending_nonce(account_address: str) -> int:
    best_nonce = -1
    last_error = None
    for rpc in LITEFORGE_RPCS:
        try:
            probe_w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
            if not probe_w3.is_connected():
                continue
            if probe_w3.eth.chain_id != LITEFORGE_CHAIN_ID:
                continue
            pending_nonce = probe_w3.eth.get_transaction_count(account_address, "pending")
            if pending_nonce > best_nonce:
                best_nonce = pending_nonce
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    if best_nonce < 0:
        raise RuntimeError(f"Cannot fetch pending nonce from LiteForge RPCs: {last_error}")
    return best_nonce


def estimate_gas_with_fallback(account_address: str, tx: dict) -> tuple[Web3, int]:
    last_error = None
    for rpc in LITEFORGE_RPCS:
        try:
            probe_w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
            if not probe_w3.is_connected():
                continue
            if probe_w3.eth.chain_id != LITEFORGE_CHAIN_ID:
                continue
            gas = probe_w3.eth.estimate_gas(tx)
            return probe_w3, gas
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    raise RuntimeError(f"Gas estimate failed for {account_address}: {last_error}")


def extract_nonce_hint(exc: Exception) -> int | None:
    text = str(exc)
    match = NONCE_HINT_RE.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def sign_and_send(account, tx: dict, log: logging.Logger):
    last_error = None
    tx_hash = None
    send_w3 = None
    current_nonce = tx["nonce"]
    for attempt in range(1, 5):
        send_tx = dict(tx)
        safe_nonce = get_safe_pending_nonce(account.address)
        if safe_nonce > current_nonce:
            log.info("Adjusted nonce before send: %s -> %s", current_nonce, safe_nonce)
            current_nonce = safe_nonce
        send_tx["nonce"] = current_nonce

        for rpc in LITEFORGE_RPCS:
            try:
                send_w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
                if not send_w3.is_connected():
                    continue
                if send_w3.eth.chain_id != LITEFORGE_CHAIN_ID:
                    continue

                rpc_pending = send_w3.eth.get_transaction_count(account.address, "pending")
                if rpc_pending > send_tx["nonce"]:
                    log.info("Adjusted nonce from RPC %s: %s -> %s", rpc, send_tx["nonce"], rpc_pending)
                    send_tx["nonce"] = rpc_pending
                    current_nonce = rpc_pending

                signed = account.sign_transaction(send_tx)
                raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
                tx_hash = send_w3.eth.send_raw_transaction(raw_tx)
                if rpc != LITEFORGE_RPCS[0]:
                    log.info("Bridge tx sent through fallback RPC: %s", rpc)
                break
            except ValueError as exc:
                last_error = exc
                msg = str(exc).lower()
                if "nonce too low" in msg:
                    hinted_nonce = extract_nonce_hint(exc)
                    if hinted_nonce is not None and hinted_nonce > current_nonce:
                        log.warning(
                            "RPC send nonce mismatch on %s: %s. Retry with nonce %s.",
                            rpc,
                            exc,
                            hinted_nonce,
                        )
                        current_nonce = hinted_nonce
                    else:
                        log.warning("RPC send nonce mismatch on %s: %s", rpc, exc)
                        current_nonce += 1
                    send_w3 = None
                    tx_hash = None
                    break
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        if tx_hash is not None and send_w3 is not None:
            break

    if tx_hash is None or send_w3 is None:
        raise RuntimeError(f"Bridge send failed on all RPCs: {last_error}")

    log.info("Bridge tx sent: %s", tx_hash.hex())
    receipt = send_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    log.info("Receipt status: %s", receipt.status)
    log.info("Block: %s", receipt.blockNumber)
    log.info("Gas used: %s", receipt.gasUsed)
    if receipt.status != 1:
        raise RuntimeError(f"Bridge transaction reverted: {tx_hash.hex()}")
    return tx_hash.hex(), receipt


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("liteforge_bridge")

    if not args.send:
        log.error("This script is for real bridge transactions. Add --send.")
        log.info("Log saved to: %s", log_file)
        return 1
    if args.amount < Decimal("0.001") or args.amount > Decimal("0.04"):
        log.error("Amount must be in range 0.001..0.04 zkLTC. Got: %s", args.amount)
        log.info("Log saved to: %s", log_file)
        return 1

    pk = read_private_key()
    account = Account.from_key(pk)
    recipient = Web3.to_checksum_address(args.recipient or account.address)
    amount_wei = int((args.amount * Decimal(10) ** 18).to_integral_value())

    log.info("Wallet: %s", account.address)
    log.info("Recipient on Sepolia: %s", recipient)
    log.info("Amount: %s zkLTC", args.amount)
    log.info("Bridge method: ArbSys.withdrawEth(address)")
    log.info("ArbSys: %s", ARBSYS)

    w3 = connect_rpc(log)
    balance = w3.eth.get_balance(account.address)
    log.info("LiteForge balance: %s zkLTC", Decimal(balance) / Decimal(10) ** 18)

    arbsys = w3.eth.contract(address=ARBSYS, abi=ARBSYS_ABI)
    nonce = get_safe_pending_nonce(account.address)
    tx = arbsys.functions.withdrawEth(recipient).build_transaction(
        {
            "from": account.address,
            "chainId": LITEFORGE_CHAIN_ID,
            "nonce": nonce,
            "value": amount_wei,
        }
    )
    try:
        gas_w3, gas = estimate_gas_with_fallback(account.address, tx)
    except RuntimeError as exc:
        log.error("Gas estimate failed: %s", exc)
        log.info("Log saved to: %s", log_file)
        return 1
    except ContractLogicError as exc:
        log.error("Bridge call reverted during gas estimate: %s", exc)
        log.info("Log saved to: %s", log_file)
        return 1
    tx["gas"] = int(gas * 1.25)
    tx = build_fee_fields(gas_w3, tx)
    max_fee = tx.get("gasPrice", tx.get("maxFeePerGas", 0)) * tx["gas"]
    total_required = amount_wei + max_fee

    log.info("Estimated gas: %s", gas)
    log.info("Gas limit used: %s", tx["gas"])
    if "gasPrice" in tx:
        log.info("Gas price wei: %s", tx["gasPrice"])
    else:
        log.info("Max fee per gas wei: %s", tx.get("maxFeePerGas"))
        log.info("Max priority fee per gas wei: %s", tx.get("maxPriorityFeePerGas"))
    log.info("Max total required: %s zkLTC", Decimal(total_required) / Decimal(10) ** 18)

    if balance < total_required:
        log.error(
            "Not enough zkLTC: need up to %s, have %s",
            Decimal(total_required) / Decimal(10) ** 18,
            Decimal(balance) / Decimal(10) ** 18,
        )
        log.info("Log saved to: %s", log_file)
        return 1

    tx_hash, _ = sign_and_send(account, tx, log)
    log.info("Bridge withdrawal initiated: %s", tx_hash)
    log.info("Explorer: https://liteforge.explorer.caldera.xyz/tx/%s", tx_hash)
    log.info("Log saved to: %s", log_file)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        logging.exception("Fatal error: %s", exc)
        sys.exit(1)
