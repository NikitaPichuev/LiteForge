from __future__ import annotations

import argparse
import logging
import pathlib
import random
import re
import sys
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation

from eth_account import Account
from web3 import Web3

from key_utils import read_private_key as read_selected_private_key


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"

CHAIN_ID = 4441
RPCS = [
    "https://liteforge.rpc.caldera.xyz/http",
    "https://liteforge.rpc.caldera.xyz/infra-partner-http",
]
EXPLORER = "https://liteforge.explorer.caldera.xyz"

ROUTER = Web3.to_checksum_address("0xF456737D17C2Bbb348fd4F7D1b000D62A46FB3b5")
WZKLTC = Web3.to_checksum_address("0x315374AA9b5536037Cc1Efeea2439CCC0913A77e")
MAX_UINT256 = 2**256 - 1
NONCE_HINT_RE = re.compile(r"(?:state|next nonce)\s*[: ]\s*(\d+)", re.IGNORECASE)

TOKENS = {
    "BRBNB": Web3.to_checksum_address("0x58B6CD7891cd0A682226E25607b958a6479195A6"),
    "LETH": Web3.to_checksum_address("0xDF474006aa807598B616500d146FfF661d644138"),
    "LITVMSWAP": Web3.to_checksum_address("0xCa4c7EdB398684cB4C5B3fD0cc6ced30b5a5f4d3"),
    "LXRP": Web3.to_checksum_address("0xfdf5cD6452EDC340e67cd16db6A9D74aaa4f81a3"),
    "ZKBTC": Web3.to_checksum_address("0xca4914407868bc37ccbE324cA149DD475d39A2Bf"),
    "ZKUSDC": Web3.to_checksum_address("0xdf69970B2fE416339187aA41D39882e864984CE9"),
    "ZKUSDT": Web3.to_checksum_address("0xa338b743Ec494ebB8345f4B6F27ffC902b7EF5Aa"),
}

ERC20_ABI = [
    {"type": "function", "name": "balanceOf", "stateMutability": "view", "inputs": [{"type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "allowance", "stateMutability": "view", "inputs": [{"type": "address"}, {"type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "approve", "stateMutability": "nonpayable", "inputs": [{"type": "address"}, {"type": "uint256"}], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "decimals", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]},
    {"type": "function", "name": "symbol", "stateMutability": "view", "inputs": [], "outputs": [{"type": "string"}]},
]

ROUTER_ABI = [
    {"type": "function", "name": "getAmountsOut", "stateMutability": "view", "inputs": [{"type": "uint256"}, {"type": "address[]"}], "outputs": [{"type": "uint256[]"}]},
    {"type": "function", "name": "swapExactETHForTokens", "stateMutability": "payable", "inputs": [{"type": "uint256"}, {"type": "address[]"}, {"type": "address"}, {"type": "uint256"}], "outputs": [{"type": "uint256[]"}]},
    {"type": "function", "name": "swapExactETHForTokensSupportingFeeOnTransferTokens", "stateMutability": "payable", "inputs": [{"type": "uint256"}, {"type": "address[]"}, {"type": "address"}, {"type": "uint256"}], "outputs": []},
]


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"litvmswap_swaps_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    return log_file


def parse_decimal(value: str, name: str) -> Decimal:
    try:
        parsed = Decimal(value.strip().replace(",", "."))
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"{name} must be a number") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"{name} must be >= 0")
    return parsed


def parse_decimal_or_range(value: str, name: str) -> Decimal:
    raw = value.strip().replace(",", ".").replace(" ", "")
    if "-" not in raw:
        return parse_decimal(raw, name)
    left, right = raw.split("-", 1)
    start = parse_decimal(left, name)
    end = parse_decimal(right, name)
    if start > end:
        start, end = end, start
    if start == end:
        return start
    precision = max(-start.as_tuple().exponent, -end.as_tuple().exponent, 6)
    scale = Decimal(10) ** precision
    start_i = int(start * scale)
    end_i = int(end * scale)
    return Decimal(random.randint(start_i, end_i)) / scale


def parse_int_or_range(value: str, name: str) -> int:
    raw = value.strip().replace(" ", "")
    if "-" not in raw:
        try:
            return int(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} must be an integer") from exc
    left, right = raw.split("-", 1)
    try:
        start = int(left)
        end = int(right)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{name} range must contain integers") from exc
    if start > end:
        start, end = end, start
    return random.randint(start, end)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LitVMSwap real swaps on LiteForge")
    parser.add_argument("--swap-token", default="random", choices=["random", *sorted(TOKENS)], help="token to buy with native zkLTC")
    parser.add_argument("--amount", required=True, type=lambda v: parse_decimal_or_range(v, "amount"), help="native zkLTC amount or range per swap")
    parser.add_argument("--swaps", default=1, type=lambda v: parse_int_or_range(v, "swaps"), help="swap count or range per wallet")
    parser.add_argument("--slippage-bps", default=300, type=int, help="slippage in basis points, default 300 = 3%")
    parser.add_argument("--send", action="store_true", help="required: send real transactions")
    return parser.parse_args()


def connect_rpc(log: logging.Logger) -> Web3:
    last_error = None
    for rpc in RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
            if w3.is_connected() and w3.eth.chain_id == CHAIN_ID:
                log.info("RPC: %s", rpc)
                return w3
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("RPC failed %s: %s", rpc, exc)
    raise RuntimeError(f"Cannot connect to LiteForge RPC: {last_error}")


def to_wei(amount: Decimal) -> int:
    return int(amount * Decimal(10**18))


def from_wei(amount: int) -> Decimal:
    return Decimal(amount) / Decimal(10**18)


def deadline() -> int:
    return int(time.time()) + 20 * 60


def get_safe_pending_nonce(account_address: str, fallback_nonce: int | None = None) -> int:
    best_nonce = -1 if fallback_nonce is None else fallback_nonce
    last_error = None
    for rpc in RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
            if not w3.is_connected() or w3.eth.chain_id != CHAIN_ID:
                continue
            pending = w3.eth.get_transaction_count(account_address, "pending")
            best_nonce = max(best_nonce, pending)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if best_nonce < 0:
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


def apply_fee_fields(w3: Web3, tx: dict) -> dict:
    tx.pop("gasPrice", None)
    tx["maxFeePerGas"] = max(int(w3.eth.gas_price), 10_000_000)
    tx["maxPriorityFeePerGas"] = 0
    return tx


def build_and_send(w3: Web3, account, tx: dict, nonce: int, label: str, log: logging.Logger) -> tuple[str, int]:
    tx = dict(tx)
    tx["chainId"] = CHAIN_ID
    tx["from"] = account.address
    tx["nonce"] = max(nonce, get_safe_pending_nonce(account.address, nonce))
    apply_fee_fields(w3, tx)
    if "gas" not in tx or int(tx.get("gas", 0)) <= 21_000:
        gas = w3.eth.estimate_gas(tx)
        tx["gas"] = int(gas * 1.25)
    log.info("%s gas limit: %s", label, tx["gas"])

    last_error = None
    for attempt in range(1, 5):
        tx["nonce"] = max(tx["nonce"], get_safe_pending_nonce(account.address, tx["nonce"]))
        signed = account.sign_transaction(tx)
        raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
        for rpc in RPCS:
            try:
                send_w3 = w3 if rpc == RPCS[0] else Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
                if not send_w3.is_connected() or send_w3.eth.chain_id != CHAIN_ID:
                    continue
                tx_hash = send_w3.eth.send_raw_transaction(raw_tx)
                if rpc != RPCS[0]:
                    log.info("%s sent through fallback RPC: %s", label, rpc)
                log.info("%s tx sent: %s", label, tx_hash.hex())
                receipt = send_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
                log.info("%s receipt status: %s", label, receipt.status)
                log.info("%s explorer: %s/tx/%s", label, EXPLORER, tx_hash.hex())
                if receipt.status != 1:
                    raise RuntimeError(f"{label} reverted: {tx_hash.hex()}")
                return tx_hash.hex(), tx["nonce"] + 1
            except ValueError as exc:
                last_error = exc
                message = str(exc).lower()
                if "nonce too low" in message:
                    hinted = extract_nonce_hint(exc)
                    tx["nonce"] = max(tx["nonce"] + 1, hinted or 0)
                    log.warning("%s nonce mismatch, retry with nonce %s", label, tx["nonce"])
                    break
                if "txpool is full" in message or "temporarily unavailable" in message:
                    log.warning("%s RPC send failed on %s: %s", label, rpc, exc)
                    continue
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                log.warning("%s send failed on %s: %s", label, rpc, exc)
                continue
        time.sleep(2)
    raise RuntimeError(f"{label} send failed: {last_error}")


def sleep_between_swaps(log: logging.Logger) -> None:
    seconds = random.uniform(2, 5)
    log.info("Pause between LitVMSwap swaps: %.1fs", seconds)
    time.sleep(seconds)


def quote_min(router, amount_in: int, path: list[str], slippage_bps: int) -> tuple[int, int]:
    amounts = router.functions.getAmountsOut(amount_in, path).call()
    out = int(amounts[-1])
    min_out = out * (10_000 - slippage_bps) // 10_000
    return out, min_out


def pick_token(requested: str) -> str:
    if requested == "random":
        return random.choice(sorted(TOKENS))
    return requested


def swap_native_to_token(
    w3: Web3,
    account,
    router,
    token_symbol: str,
    amount_wei: int,
    nonce: int,
    args: argparse.Namespace,
    log: logging.Logger,
) -> int:
    token = TOKENS[token_symbol]
    path = [WZKLTC, token]
    quoted, min_out = quote_min(router, amount_wei, path, args.slippage_bps)
    log.info(
        "Swap zkLTC -> %s: %s zkLTC, quoted %s %s, min %s",
        token_symbol,
        from_wei(amount_wei),
        from_wei(quoted),
        token_symbol,
        from_wei(min_out),
    )
    tx = router.functions.swapExactETHForTokens(min_out, path, account.address, deadline()).build_transaction(
        {"from": account.address, "value": amount_wei, "gas": 1}
    )
    _, nonce = build_and_send(w3, account, tx, nonce, f"litvmswap-zkLTC-{token_symbol}", log)
    return nonce


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("litvmswap")
    try:
        if not args.send:
            log.error("This script sends real LitVMSwap transactions. Add --send.")
            return 1
        if args.slippage_bps < 1 or args.slippage_bps > 2000:
            log.error("Slippage must be 1..2000 bps")
            return 1
        if args.swaps < 1 or args.swaps > 20:
            log.error("Swaps per wallet must be 1..20")
            return 1
        if args.amount <= 0:
            log.error("Amount must be greater than 0")
            return 1

        w3 = connect_rpc(log)
        account = Account.from_key(read_selected_private_key())
        router = w3.eth.contract(address=ROUTER, abi=ROUTER_ABI)
        nonce = get_safe_pending_nonce(account.address)

        log.info("Wallet: %s", account.address)
        log.info("LitVMSwap router: %s", ROUTER)
        log.info("Wrapped native: %s", WZKLTC)
        log.info("Swaps per wallet: %s", args.swaps)
        log.info("Amount per swap: %s zkLTC", args.amount)
        log.info("Slippage: %s bps", args.slippage_bps)
        log.info("Mode: SEND")

        balance = w3.eth.get_balance(account.address)
        needed = to_wei(args.amount) * args.swaps
        log.info("Native balance: %s zkLTC", from_wei(balance))
        if balance <= needed:
            raise RuntimeError(f"Native balance is too low for swaps: need > {from_wei(needed)} zkLTC plus gas")

        for index in range(1, args.swaps + 1):
            token_symbol = pick_token(args.swap_token)
            log.info("[swap %s/%s] target token: %s", index, args.swaps, token_symbol)
            nonce = swap_native_to_token(w3, account, router, token_symbol, to_wei(args.amount), nonce, args, log)
            if index < args.swaps:
                sleep_between_swaps(log)

        log.info("LitVMSwap swaps completed")
        return 0
    except Exception as exc:  # noqa: BLE001
        log.exception("Fatal error: %s", exc)
        return 1
    finally:
        log.info("Log saved to: %s", log_file)


if __name__ == "__main__":
    sys.exit(main())
