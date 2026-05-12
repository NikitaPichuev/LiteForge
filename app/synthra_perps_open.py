"""
Open a Synthra BTC-PERP position on Arc Testnet through JSON-RPC.

Default mode is dry-run: it validates inputs, checks balance/allowance,
builds the transaction and estimates gas, but does not sign or send.
Add --send to broadcast.
"""
from __future__ import annotations

import argparse
import logging
import pathlib
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

from eth_account import Account
from web3 import Web3

from key_utils import read_private_key as read_selected_private_key


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
KEYS_FILE = PROJECT_ROOT / "keys.txt"

ARC_RPC = "https://rpc.testnet.arc.network"
ARC_CHAIN_ID = 5042002

ORDER_ROUTER = Web3.to_checksum_address("0xADDE8a35A94ea4fC588FCaa34CD802f3afa6DA66")
BTC_POOL_TOKEN = Web3.to_checksum_address("0xac36804b4a860c5463f3b89d077a0653aaa9d8f1")
BTC_INDEX_TOKEN = Web3.to_checksum_address("0x2260fac5e5542a773Aa44fBCfeDf7C193bc2C599")
USDC = Web3.to_checksum_address("0x3600000000000000000000000000000000000000")

USDC_DECIMALS = Decimal("1000000")
USD_30_DECIMALS = Decimal("1000000000000000000000000000000")
MAX_UINT256 = 2**256 - 1
MIN_MARGIN_USDC = Decimal("0.1")
MAX_MARGIN_USDC = Decimal("2")
MIN_LEVERAGE = Decimal("1")
MAX_LEVERAGE = Decimal("50")


ORDER_ROUTER_ABI = [
    {
        "type": "function",
        "name": "minExecutionFee",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "createIncreaseOrder",
        "stateMutability": "payable",
        "inputs": [
            {"name": "_poolToken", "type": "address"},
            {"name": "_path", "type": "address[]"},
            {"name": "_amountIn", "type": "uint256"},
            {"name": "_indexToken", "type": "address"},
            {"name": "_minOut", "type": "uint256"},
            {"name": "_sizeDelta", "type": "uint256"},
            {"name": "_collateralToken", "type": "address"},
            {"name": "_isLong", "type": "bool"},
            {"name": "_triggerPrice", "type": "uint256"},
            {"name": "_triggerAboveThreshold", "type": "bool"},
            {"name": "_executionFee", "type": "uint256"},
            {"name": "_shouldWrap", "type": "bool"},
        ],
        "outputs": [],
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


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"synthra_perps_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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
    parser = argparse.ArgumentParser(description="Open Synthra BTC-PERP position via RPC")
    parser.add_argument("--side", required=True, choices=["long", "short"], help="position side")
    parser.add_argument("--margin", required=True, type=lambda v: parse_decimal(v, "margin"), help="USDC margin, 0.1..2")
    parser.add_argument("--leverage", default=Decimal("25"), type=lambda v: parse_decimal(v, "leverage"), help="leverage, 1..50")
    parser.add_argument("--send", action="store_true", help="sign and broadcast transaction")
    parser.add_argument("--approve", action="store_true", help="approve USDC to OrderRouter if allowance is too low")
    return parser.parse_args()


def build_fee_fields(w3: Web3, tx: dict) -> dict:
    if "maxFeePerGas" in tx or "maxPriorityFeePerGas" in tx:
        tx.pop("gasPrice", None)
        tx.setdefault("maxFeePerGas", w3.eth.gas_price)
        tx.setdefault("maxPriorityFeePerGas", 0)
    else:
        tx["gasPrice"] = w3.eth.gas_price
    return tx


def sign_and_send(w3: Web3, account, tx: dict, label: str, log: logging.Logger):
    signed = account.sign_transaction(tx)
    raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
    tx_hash = w3.eth.send_raw_transaction(raw_tx)
    log.info("%s tx sent: %s", label, tx_hash.hex())
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    log.info("%s receipt status: %s", label, receipt.status)
    log.info("%s block: %s", label, receipt.blockNumber)
    log.info("%s gas used: %s", label, receipt.gasUsed)
    if receipt.status != 1:
        raise RuntimeError(f"{label} transaction reverted: {tx_hash.hex()}")
    return receipt, tx_hash.hex()


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("synthra_perps")

    if args.margin < MIN_MARGIN_USDC or args.margin > MAX_MARGIN_USDC:
        log.error("Margin must be in range %s..%s USDC. Got: %s", MIN_MARGIN_USDC, MAX_MARGIN_USDC, args.margin)
        log.info("Log saved to: %s", log_file)
        return 1
    if args.leverage < MIN_LEVERAGE or args.leverage > MAX_LEVERAGE:
        log.error("Leverage must be in range %s..%s. Got: %s", MIN_LEVERAGE, MAX_LEVERAGE, args.leverage)
        log.info("Log saved to: %s", log_file)
        return 1

    amount_in = int((args.margin * USDC_DECIMALS).to_integral_value())
    size_delta = int((args.margin * args.leverage * USD_30_DECIMALS).to_integral_value())
    is_long = args.side == "long"

    pk = read_private_key()
    account = Account.from_key(pk)

    log.info("Wallet: %s", account.address)
    log.info("Market: BTC-PERP")
    log.info("Side: %s", args.side.upper())
    log.info("Margin USDC: %s", args.margin)
    log.info("Leverage: %sx", args.leverage)
    log.info("Position size USD: %s", args.margin * args.leverage)
    log.info("Mode: %s", "SEND" if args.send else "DRY-RUN")

    w3 = Web3(Web3.HTTPProvider(ARC_RPC, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        log.error("Cannot connect to RPC: %s", ARC_RPC)
        log.info("Log saved to: %s", log_file)
        return 1
    chain_id = w3.eth.chain_id
    if chain_id != ARC_CHAIN_ID:
        log.error("Wrong chain id: got %s, expected %s", chain_id, ARC_CHAIN_ID)
        log.info("Log saved to: %s", log_file)
        return 1

    order_router = w3.eth.contract(address=ORDER_ROUTER, abi=ORDER_ROUTER_ABI)
    usdc = w3.eth.contract(address=USDC, abi=ERC20_ABI)

    balance = usdc.functions.balanceOf(account.address).call()
    allowance = usdc.functions.allowance(account.address, ORDER_ROUTER).call()
    execution_fee = order_router.functions.minExecutionFee().call()

    log.info("USDC balance: %.6f", balance / 1_000_000)
    log.info("USDC allowance to OrderRouter: %.6f", allowance / 1_000_000)
    log.info("Required margin units: %s", amount_in)
    log.info("Required execution fee wei: %s", execution_fee)

    if balance < amount_in:
        log.error("Not enough USDC: need %.6f, have %.6f", amount_in / 1_000_000, balance / 1_000_000)
        log.info("Log saved to: %s", log_file)
        return 1

    nonce = w3.eth.get_transaction_count(account.address, "pending")
    if allowance < amount_in:
        log.warning("USDC allowance is too low for this order.")
        if not args.approve:
            log.error("Run again with --approve to approve OrderRouter, or approve manually in the wallet.")
            log.info("Log saved to: %s", log_file)
            return 1

        approve_call = usdc.functions.approve(ORDER_ROUTER, MAX_UINT256)
        approve_tx = approve_call.build_transaction(
            {
                "from": account.address,
                "chainId": ARC_CHAIN_ID,
                "nonce": nonce,
                "value": 0,
            }
        )
        approve_gas = w3.eth.estimate_gas(approve_tx)
        approve_tx["gas"] = int(approve_gas * 1.2)
        approve_tx = build_fee_fields(w3, approve_tx)
        log.info("Approve estimated gas: %s", approve_gas)
        if not args.send:
            log.info("Dry-run: approve transaction was built but not sent.")
            log.info("Log saved to: %s", log_file)
            return 0
        sign_and_send(w3, account, approve_tx, "Approve", log)
        nonce += 1

    call = order_router.functions.createIncreaseOrder(
        BTC_POOL_TOKEN,
        [USDC],
        amount_in,
        BTC_INDEX_TOKEN,
        0,
        size_delta,
        USDC,
        is_long,
        0,
        True,
        execution_fee,
        False,
    )
    tx = call.build_transaction(
        {
            "from": account.address,
            "chainId": ARC_CHAIN_ID,
            "nonce": nonce,
            "value": execution_fee,
        }
    )
    gas = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas * 1.2)
    tx = build_fee_fields(w3, tx)

    log.info("OrderRouter: %s", ORDER_ROUTER)
    log.info("Amount in units: %s", amount_in)
    log.info("Size delta 1e30: %s", size_delta)
    log.info("Estimated gas: %s", gas)
    log.info("Gas limit used: %s", tx["gas"])
    if "gasPrice" in tx:
        log.info("Gas price wei: %s", tx["gasPrice"])
    else:
        log.info("Max fee per gas wei: %s", tx.get("maxFeePerGas"))
        log.info("Max priority fee per gas wei: %s", tx.get("maxPriorityFeePerGas"))

    if not args.send:
        log.info("Dry-run complete. Add --send to broadcast.")
        log.info("Log saved to: %s", log_file)
        return 0

    _, tx_hash = sign_and_send(w3, account, tx, "Open position", log)
    log.info("Open position OK: %s", tx_hash)
    log.info("Explorer: https://arc-testnet-explorer.stg.blockchain.circle.com/tx/%s", tx_hash)
    log.info("Log saved to: %s", log_file)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        logging.exception("Fatal error: %s", exc)
        sys.exit(1)
