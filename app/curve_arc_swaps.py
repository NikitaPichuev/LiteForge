"""
Small real Curve swaps on Arc Testnet.

Uses configured Curve pools on Arc Testnet. The ARC token from the shared URL
has no available Curve route/pool at the time this script was added.
"""
from __future__ import annotations

import argparse
import logging
import pathlib
import random
import sys
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation

from eth_account import Account
from web3 import Web3

from key_utils import read_private_key as read_selected_private_key


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
KEYS_FILE = PROJECT_ROOT / "keys.txt"

ARC_RPC = "https://arc-testnet.drpc.org"
ARC_RPCS = [
    "https://arc-testnet.drpc.org",
    "https://rpc.testnet.arc.network",
    "https://rpc.quicknode.testnet.arc.network",
    "https://rpc.blockdaemon.testnet.arc.network",
]
ARC_CHAIN_ID = 5042002

USDC = Web3.to_checksum_address("0x3600000000000000000000000000000000000000")
EURC = Web3.to_checksum_address("0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a")
WUSDC = Web3.to_checksum_address("0x911b4000D3422F482F4062a913885f7b035382Df")
RUSDC = Web3.to_checksum_address("0xAAC9c6387FFd1F840dA9F4E0F69E9838d4cB6Be0")
MAX_UINT256 = 2**256 - 1


POOL_ABI = [
    {
        "type": "function",
        "name": "coins",
        "stateMutability": "view",
        "inputs": [{"name": "arg0", "type": "uint256"}],
        "outputs": [{"type": "address"}],
    },
    {
        "type": "function",
        "name": "get_dy",
        "stateMutability": "view",
        "inputs": [
            {"name": "i", "type": "int128"},
            {"name": "j", "type": "int128"},
            {"name": "dx", "type": "uint256"},
        ],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "exchange",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "i", "type": "int128"},
            {"name": "j", "type": "int128"},
            {"name": "dx", "type": "uint256"},
            {"name": "min_dy", "type": "uint256"},
        ],
        "outputs": [{"type": "uint256"}],
    },
]


ERC20_ABI = [
    {
        "type": "function",
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "allowance",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "approve",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"type": "bool"}],
    },
]


TOKENS = {
    "USDC": {"address": USDC, "decimals": 6, "coin_index": 0},
    "EURC": {"address": EURC, "decimals": 6, "coin_index": 1},
    "WUSDC": {"address": WUSDC, "decimals": 18, "coin_index": 0},
    "rUSDC": {"address": RUSDC, "decimals": 18, "coin_index": 1},
}


ROUTES = {
    "USDC": {
        "to": "EURC",
        "pool": Web3.to_checksum_address("0x2D84D79C852f6842AbE0304b70bBaA1506AdD457"),
        "i": 0,
        "j": 1,
        "name": "USDC/EURC",
    },
    "EURC": {
        "to": "USDC",
        "pool": Web3.to_checksum_address("0x2D84D79C852f6842AbE0304b70bBaA1506AdD457"),
        "i": 1,
        "j": 0,
        "name": "USDC/EURC",
    },
    "WUSDC": {
        "to": "EURC",
        "pool": Web3.to_checksum_address("0x942644106B073E30D72c2C5D7529D5C296ea91ab"),
        "i": 0,
        "j": 1,
        "name": "WUSDC/EURC",
    },
    "rUSDC": {
        "to": "WUSDC",
        "pool": Web3.to_checksum_address("0xa87680b380207f6eb2ab0613401277124659d7F3"),
        "i": 1,
        "j": 0,
        "name": "WUSDC/rUSDC",
    },
}


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"curve_arc_swaps_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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
    parser = argparse.ArgumentParser(description="Run small real Curve swaps on Arc")
    parser.add_argument("--amount-usdc", default=Decimal("0.01"), type=lambda v: parse_decimal(v, "amount-usdc"))
    parser.add_argument("--start-token", default="USDC", choices=sorted(TOKENS))
    parser.add_argument("--amount-token", default=None, type=lambda v: parse_decimal(v, "amount-token"))
    parser.add_argument("--swaps", default=3, type=int, help="number of real swaps, 2..3")
    parser.add_argument("--slippage-bps", default=100, type=int, help="max slippage in bps, 100 = 1%%")
    parser.add_argument("--send", action="store_true", help="required: send real transactions")
    return parser.parse_args()


def build_fee_fields(w3: Web3, tx: dict) -> dict:
    if "maxFeePerGas" in tx or "maxPriorityFeePerGas" in tx:
        tx.pop("gasPrice", None)
        tx.setdefault("maxFeePerGas", w3.eth.gas_price)
        tx.setdefault("maxPriorityFeePerGas", 0)
    else:
        tx["gasPrice"] = w3.eth.gas_price
    return tx


def get_safe_pending_nonce(account_address: str, fallback_nonce: int | None = None) -> int:
    best_nonce = -1 if fallback_nonce is None else fallback_nonce
    last_error = None
    for rpc_url in ARC_RPCS:
        probe_w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        try:
            pending_nonce = probe_w3.eth.get_transaction_count(account_address, "pending")
            if pending_nonce > best_nonce:
                best_nonce = pending_nonce
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    if best_nonce < 0:
        raise RuntimeError(f"Cannot fetch pending nonce from Arc RPCs: {last_error}")
    return best_nonce


def sign_and_send(w3: Web3, account, tx: dict, label: str, log: logging.Logger):
    signed = account.sign_transaction(tx)
    raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
    last_error = None
    tx_hash = None
    send_w3 = w3
    for rpc_url in ARC_RPCS:
        send_w3 = w3 if rpc_url == ARC_RPC else Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        try:
            tx_hash = send_w3.eth.send_raw_transaction(raw_tx)
            if rpc_url != ARC_RPC:
                log.info("%s sent through fallback RPC: %s", label, rpc_url)
            break
        except ValueError as exc:
            last_error = exc
            msg = str(exc).lower()
            if "txpool is full" in msg or "temporarily unavailable" in msg or "timeout" in msg:
                log.warning("%s RPC send failed on %s: %s", label, rpc_url, exc)
                continue
            raise
    if tx_hash is None:
        raise RuntimeError(f"{label} send failed on all RPCs: {last_error}")
    log.info("%s sent: %s", label, tx_hash.hex())
    receipt = send_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    log.info("%s receipt status: %s", label, receipt.status)
    log.info("%s block: %s", label, receipt.blockNumber)
    log.info("%s gas used: %s", label, receipt.gasUsed)
    if receipt.status != 1:
        raise RuntimeError(f"{label} reverted: {tx_hash.hex()}")
    return tx_hash.hex(), receipt


def units_to_amount(units: int, decimals: int) -> Decimal:
    return Decimal(units) / (Decimal(10) ** decimals)


def approve_if_needed(w3, account, token, token_symbol: str, spender: str, amount: int, nonce: int, send: bool, log):
    allowance = token.functions.allowance(account.address, spender).call()
    log.info("%s allowance to Curve pool %s: %s", token_symbol, spender, allowance)
    if allowance >= amount:
        return nonce

    log.info("Approving %s to Curve pool %s...", token_symbol, spender)
    safe_nonce = get_safe_pending_nonce(account.address, nonce)
    if safe_nonce != nonce:
        log.info("Adjusted nonce before approve %s: %s -> %s", token_symbol, nonce, safe_nonce)
    tx = token.functions.approve(spender, MAX_UINT256).build_transaction(
        {
            "from": account.address,
            "chainId": ARC_CHAIN_ID,
            "nonce": safe_nonce,
            "value": 0,
        }
    )
    gas = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas * 1.2)
    tx = build_fee_fields(w3, tx)
    log.info("Approve %s estimated gas: %s", token_symbol, gas)
    if not send:
        raise RuntimeError("Refusing to continue without --send")
    sign_and_send(w3, account, tx, f"Approve {token_symbol}", log)
    return max(safe_nonce + 1, get_safe_pending_nonce(account.address, safe_nonce + 1))


def sleep_between_actions(log: logging.Logger) -> None:
    delay = random.uniform(2, 5)
    log.info("Pause between actions: %.1fs", delay)
    time.sleep(delay)


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("curve_arc")

    if not args.send:
        log.error("This script is for real swaps. Add --send.")
        log.info("Log saved to: %s", log_file)
        return 1
    if args.swaps < 2 or args.swaps > 3:
        log.error("Swaps must be 2 or 3. Got: %s", args.swaps)
        log.info("Log saved to: %s", log_file)
        return 1
    if args.start_token == "USDC" and (args.amount_usdc < Decimal("0.001") or args.amount_usdc > Decimal("2")):
        log.error("Amount must be in range 0.001..2 USDC. Got: %s", args.amount_usdc)
        log.info("Log saved to: %s", log_file)
        return 1
    if args.slippage_bps < 1 or args.slippage_bps > 1000:
        log.error("Slippage must be in range 1..1000 bps. Got: %s", args.slippage_bps)
        log.info("Log saved to: %s", log_file)
        return 1

    pk = read_private_key()
    account = Account.from_key(pk)
    w3 = Web3(Web3.HTTPProvider(ARC_RPC, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        log.error("Cannot connect to RPC: %s", ARC_RPC)
        log.info("Log saved to: %s", log_file)
        return 1
    if w3.eth.chain_id != ARC_CHAIN_ID:
        log.error("Wrong chain id: got %s, expected %s", w3.eth.chain_id, ARC_CHAIN_ID)
        log.info("Log saved to: %s", log_file)
        return 1

    token_contracts = {
        symbol: w3.eth.contract(address=data["address"], abi=ERC20_ABI)
        for symbol, data in TOKENS.items()
    }

    log.info("Wallet: %s", account.address)
    log.info("Supported start tokens: %s", ", ".join(sorted(TOKENS)))
    log.info("Swaps: %s", args.swaps)
    log.info("Start token: %s", args.start_token)
    log.info("Start amount USDC setting: %s", args.amount_usdc)
    log.info("Slippage: %s bps", args.slippage_bps)

    balances = {
        symbol: token_contracts[symbol].functions.balanceOf(account.address).call()
        for symbol in TOKENS
    }
    for symbol, balance in balances.items():
        log.info("%s balance before: %s", symbol, units_to_amount(balance, TOKENS[symbol]["decimals"]))

    start_symbol = args.start_token
    if args.amount_token is None:
        start_amount = args.amount_usdc if start_symbol == "USDC" else units_to_amount(balances[start_symbol], TOKENS[start_symbol]["decimals"])
    else:
        start_amount = args.amount_token
    start_units = int((start_amount * Decimal(10) ** TOKENS[start_symbol]["decimals"]).to_integral_value())
    if balances[start_symbol] < start_units:
        log.error(
            "Not enough %s: need %s, have %s",
            start_symbol,
            start_amount,
            units_to_amount(balances[start_symbol], TOKENS[start_symbol]["decimals"]),
        )
        log.info("Log saved to: %s", log_file)
        return 1

    nonce = get_safe_pending_nonce(account.address)
    current_symbol = start_symbol
    amount_in = start_units

    for step in range(1, args.swaps + 1):
        if current_symbol not in ROUTES:
            log.error("No Curve route configured for %s", current_symbol)
            log.info("Log saved to: %s", log_file)
            return 1

        route = ROUTES[current_symbol]
        next_symbol = route["to"]
        pool_address = route["pool"]
        pool = w3.eth.contract(address=pool_address, abi=POOL_ABI)
        i = route["i"]
        j = route["j"]
        token_in = token_contracts[current_symbol]
        token_out = token_contracts[next_symbol]

        current_balance = token_in.functions.balanceOf(account.address).call()
        if current_balance < amount_in:
            amount_in = current_balance
        if amount_in <= 0:
            log.error("No %s balance for swap step %s", current_symbol, step)
            log.info("Log saved to: %s", log_file)
            return 1

        quoted = pool.functions.get_dy(i, j, amount_in).call()
        min_dy = quoted * (10000 - args.slippage_bps) // 10000
        log.info(
            "Swap %s/%s via %s (%s): %s %s -> quoted %s %s, min %s %s",
            step,
            args.swaps,
            route["name"],
            pool_address,
            units_to_amount(amount_in, TOKENS[current_symbol]["decimals"]),
            current_symbol,
            units_to_amount(quoted, TOKENS[next_symbol]["decimals"]),
            next_symbol,
            units_to_amount(min_dy, TOKENS[next_symbol]["decimals"]),
            next_symbol,
        )

        nonce = approve_if_needed(w3, account, token_in, current_symbol, pool_address, amount_in, nonce, args.send, log)
        out_before = token_out.functions.balanceOf(account.address).call()
        sleep_between_actions(log)
        safe_nonce = get_safe_pending_nonce(account.address, nonce)
        if safe_nonce != nonce:
            log.info("Adjusted nonce before swap %s: %s -> %s", step, nonce, safe_nonce)
        tx = pool.functions.exchange(i, j, amount_in, min_dy).build_transaction(
            {
                "from": account.address,
                "chainId": ARC_CHAIN_ID,
                "nonce": safe_nonce,
                "value": 0,
            }
        )
        gas = w3.eth.estimate_gas(tx)
        tx["gas"] = int(gas * 1.2)
        tx = build_fee_fields(w3, tx)
        log.info("Swap %s estimated gas: %s", step, gas)
        tx_hash, _ = sign_and_send(w3, account, tx, f"Swap {step}", log)
        log.info("Explorer: https://testnet.arcscan.app/tx/%s", tx_hash)
        nonce = max(safe_nonce + 1, get_safe_pending_nonce(account.address, safe_nonce + 1))

        out_after = token_out.functions.balanceOf(account.address).call()
        received = max(0, out_after - out_before)
        log.info("Swap %s received: %s %s", step, units_to_amount(received, TOKENS[next_symbol]["decimals"]), next_symbol)
        current_symbol = next_symbol
        amount_in = received
        if step < args.swaps:
            sleep_between_actions(log)

    for symbol, token in token_contracts.items():
        balance = token.functions.balanceOf(account.address).call()
        log.info("%s balance after: %s", symbol, units_to_amount(balance, TOKENS[symbol]["decimals"]))
    log.info("Curve swaps completed.")
    log.info("Log saved to: %s", log_file)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        logging.exception("Fatal error: %s", exc)
        sys.exit(1)
