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

ROUTER = Web3.to_checksum_address("0xd28967D75750f477E450Df81C73f34E2713B86B4")
WZKLTC = Web3.to_checksum_address("0x4Fd3765cde8D1d2BE4EdbaA03940AfC56794c304")
FARMING = Web3.to_checksum_address("0x28c7167ebF6112D5B01396eEeDFe8F990Fcb54bb")
CASINO = Web3.to_checksum_address("0x5Be451a79E790a2D31FD5Db5C439D6E177987b2b")
MAX_UINT256 = 2**256 - 1
NONCE_HINT_RE = re.compile(r"(?:state|next nonce)\s*[: ]\s*(\d+)", re.IGNORECASE)

TOKENS = {
    "BNB": Web3.to_checksum_address("0x31351646e2c5479A30f846dFa4297E9Dbe189a63"),
    "MON": Web3.to_checksum_address("0xa12C18847c41ECE267155ffAe112b8951AbbcA1C"),
    "HYPE": Web3.to_checksum_address("0xBB3B44EB672650Fb4a1Cf6D9dc5d3b7494F333AB"),
    "ETH": Web3.to_checksum_address("0x5b0AE944A4Ee6241a5A638C440A0dCD42411bD3C"),
    "LITVM": Web3.to_checksum_address("0xF143eCFE3DFEEB4ae188cA4f1c7c7ab0b5F592eb"),
    "WDEX": Web3.to_checksum_address("0xEa71393074fFCB6d132B8a2b6028CAF952af03A5"),
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
    {"type": "function", "name": "addLiquidityETH", "stateMutability": "payable", "inputs": [{"type": "address"}, {"type": "uint256"}, {"type": "uint256"}, {"type": "uint256"}, {"type": "address"}, {"type": "uint256"}], "outputs": [{"type": "uint256"}, {"type": "uint256"}, {"type": "uint256"}]},
]

FARMING_ABI = [
    {"type": "function", "name": "poolInfo", "stateMutability": "view", "inputs": [{"type": "uint256"}], "outputs": [{"type": "address"}, {"type": "address"}, {"type": "uint256"}, {"type": "uint256"}, {"type": "uint256"}, {"type": "uint256"}]},
    {"type": "function", "name": "userInfo", "stateMutability": "view", "inputs": [{"type": "uint256"}, {"type": "address"}], "outputs": [{"type": "uint256"}, {"type": "uint256"}]},
    {"type": "function", "name": "deposit", "stateMutability": "nonpayable", "inputs": [{"type": "uint256"}, {"type": "uint256"}], "outputs": []},
]

CASINO_ABI = [
    {"type": "function", "name": "minBet", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "maxBet", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "isActive", "stateMutability": "view", "inputs": [], "outputs": [{"type": "bool"}]},
    {"type": "function", "name": "playCoinflip", "stateMutability": "payable", "inputs": [{"type": "bool"}], "outputs": []},
]


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"wolfdex_actions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WolfDex LiteForge real actions")
    parser.add_argument("--swap-amount", required=True, type=lambda v: parse_decimal_or_range(v, "swap-amount"), help="zkLTC amount or range for main swap")
    parser.add_argument("--swap-token", default="LITVM", choices=["random", *sorted(TOKENS)], help="token to buy from zkLTC")
    parser.add_argument("--litvm-swap-amount", default=Decimal("0"), type=lambda v: parse_decimal_or_range(v, "litvm-swap-amount"), help="extra zkLTC -> LITVM amount/range; 0 disables")
    parser.add_argument("--liquidity-amount", default=Decimal("0"), type=lambda v: parse_decimal_or_range(v, "liquidity-amount"), help="zkLTC side amount/range for zkLTC/LITVM liquidity; 0 disables")
    parser.add_argument("--stake-pct", default=Decimal("50"), type=lambda v: parse_decimal_or_range(v, "stake-pct"), help="percent/range of remaining LITVM to stake; 0 disables")
    parser.add_argument("--casino-bet", default=Decimal("0"), type=lambda v: parse_decimal_or_range(v, "casino-bet"), help="zkLTC coinflip bet/range; 0 disables")
    parser.add_argument("--slippage-bps", default=300, type=int)
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


def token_contract(w3: Web3, token: str):
    return w3.eth.contract(address=Web3.to_checksum_address(token), abi=ERC20_ABI)


def ensure_allowance(w3: Web3, account, token: str, spender: str, amount: int, nonce: int, log: logging.Logger) -> int:
    contract = token_contract(w3, token)
    allowance = contract.functions.allowance(account.address, spender).call()
    if allowance >= amount:
        return nonce
    tx = contract.functions.approve(spender, MAX_UINT256).build_transaction({"from": account.address, "gas": 1})
    log.info("Approve %s to %s", token, spender)
    _, nonce = build_and_send(w3, account, tx, nonce, "approve", log)
    sleep_between_actions(log)
    return nonce


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
    log.info("%s estimated gas/limit: %s/%s", label, int(tx["gas"] / 1.25), tx["gas"])
    log.info("%s native value wei: %s", label, tx.get("value", 0))

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
                log.info("%s block: %s", label, receipt.blockNumber)
                log.info("%s gas used: %s", label, receipt.gasUsed)
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


def sleep_between_actions(log: logging.Logger) -> None:
    seconds = random.uniform(2, 5)
    log.info("Pause between WolfDex actions: %.1fs", seconds)
    time.sleep(seconds)


def quote_min(router, amount_in: int, path: list[str], slippage_bps: int) -> tuple[int, int]:
    amounts = router.functions.getAmountsOut(amount_in, path).call()
    out = int(amounts[-1])
    min_out = out * (10_000 - slippage_bps) // 10_000
    return out, min_out


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
    log.info("Swap zkLTC -> %s: %s zkLTC, quoted %s %s, min %s", token_symbol, from_wei(amount_wei), from_wei(quoted), token_symbol, min_out)
    tx = router.functions.swapExactETHForTokens(min_out, path, account.address, deadline()).build_transaction(
        {"from": account.address, "value": amount_wei, "gas": 1}
    )
    _, nonce = build_and_send(w3, account, tx, nonce, f"swap-zkLTC-{token_symbol}", log)
    return nonce


def add_liquidity_litvm(w3: Web3, account, router, amount_wei: int, nonce: int, args: argparse.Namespace, log: logging.Logger) -> int:
    litvm = TOKENS["LITVM"]
    litvm_contract = token_contract(w3, litvm)
    litvm_balance = litvm_contract.functions.balanceOf(account.address).call()
    if litvm_balance <= 0:
        log.warning("Liquidity skipped: no LITVM balance")
        return nonce

    quoted_token, _ = quote_min(router, amount_wei, [WZKLTC, litvm], args.slippage_bps)
    token_desired = min(quoted_token, litvm_balance)
    token_min = token_desired * (10_000 - args.slippage_bps) // 10_000
    eth_min = amount_wei * (10_000 - args.slippage_bps) // 10_000
    log.info("Add liquidity zkLTC/LITVM: %s zkLTC + %s LITVM", from_wei(amount_wei), from_wei(token_desired))

    nonce = ensure_allowance(w3, account, litvm, ROUTER, token_desired, nonce, log)
    tx = router.functions.addLiquidityETH(
        litvm,
        token_desired,
        token_min,
        eth_min,
        account.address,
        deadline(),
    ).build_transaction({"from": account.address, "value": amount_wei, "gas": 1})
    _, nonce = build_and_send(w3, account, tx, nonce, "add-liquidity-LITVM", log)
    return nonce


def stake_litvm(w3: Web3, account, farm, stake_pct: Decimal, nonce: int, log: logging.Logger) -> int:
    if stake_pct <= 0:
        log.info("Stake skipped: stake pct is 0")
        return nonce
    if stake_pct > 100:
        stake_pct = Decimal("100")

    pid = 0
    staking_token, reward_token, *_ = farm.functions.poolInfo(pid).call()
    if staking_token.lower() != TOKENS["LITVM"].lower() or reward_token.lower() != TOKENS["LITVM"].lower():
        log.warning("Stake skipped: farming pid 0 is not LITVM/LITVM")
        return nonce
    litvm_contract = token_contract(w3, TOKENS["LITVM"])
    balance = litvm_contract.functions.balanceOf(account.address).call()
    amount = int(Decimal(balance) * stake_pct / Decimal(100))
    if amount <= 0:
        log.warning("Stake skipped: no LITVM balance")
        return nonce
    log.info("Stake LITVM: %s%% of balance = %s LITVM", stake_pct, from_wei(amount))
    nonce = ensure_allowance(w3, account, TOKENS["LITVM"], FARMING, amount, nonce, log)
    tx = farm.functions.deposit(pid, amount).build_transaction({"from": account.address, "gas": 1})
    _, nonce = build_and_send(w3, account, tx, nonce, "stake-LITVM", log)
    return nonce


def casino_coinflip(w3: Web3, account, casino, bet_wei: int, nonce: int, log: logging.Logger) -> int:
    if bet_wei <= 0:
        log.info("Casino skipped: bet is 0")
        return nonce
    min_bet = casino.functions.minBet().call()
    max_bet = casino.functions.maxBet().call()
    active = casino.functions.isActive().call()
    log.info("Casino min/max/active: %s/%s/%s", from_wei(min_bet), from_wei(max_bet), active)
    if not active:
        log.warning("Casino skipped: inactive")
        return nonce
    if bet_wei < min_bet or bet_wei > max_bet:
        log.warning("Casino skipped: bet %s outside %s..%s zkLTC", from_wei(bet_wei), from_wei(min_bet), from_wei(max_bet))
        return nonce
    heads = random.choice([True, False])
    log.info("Coinflip bet: %s zkLTC, side: %s", from_wei(bet_wei), "heads" if heads else "tails")
    tx = casino.functions.playCoinflip(heads).build_transaction({"from": account.address, "value": bet_wei, "gas": 1})
    _, nonce = build_and_send(w3, account, tx, nonce, "casino-coinflip", log)
    return nonce


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("wolfdex")
    try:
        if not args.send:
            log.error("This script sends real WolfDex transactions. Add --send.")
            return 1
        if args.slippage_bps < 1 or args.slippage_bps > 2000:
            log.error("Slippage must be 1..2000 bps")
            return 1
        if args.swap_amount <= 0:
            log.error("swap-amount must be greater than 0")
            return 1
        if args.swap_amount > Decimal("0.05") or args.litvm_swap_amount > Decimal("0.05") or args.liquidity_amount > Decimal("0.05"):
            log.error("WolfDex script limits swap/liquidity amounts to <= 0.05 zkLTC")
            return 1

        w3 = connect_rpc(log)
        pk = read_selected_private_key()
        account = Account.from_key(pk)
        router = w3.eth.contract(address=ROUTER, abi=ROUTER_ABI)
        farm = w3.eth.contract(address=FARMING, abi=FARMING_ABI)
        casino = w3.eth.contract(address=CASINO, abi=CASINO_ABI)
        nonce = get_safe_pending_nonce(account.address)

        token_symbol = random.choice(sorted(TOKENS)) if args.swap_token == "random" else args.swap_token
        log.info("Wallet: %s", account.address)
        log.info("Router: %s", ROUTER)
        log.info("Farming: %s", FARMING)
        log.info("Casino: %s", CASINO)
        log.info("Main swap token: %s", token_symbol)
        log.info("Selected main swap amount: %s zkLTC", args.swap_amount)
        log.info("Selected extra LITVM swap amount: %s zkLTC", args.litvm_swap_amount)
        log.info("Selected liquidity amount: %s zkLTC", args.liquidity_amount)
        log.info("Selected stake percent: %s", args.stake_pct)
        log.info("Selected casino bet: %s zkLTC", args.casino_bet)
        log.info("Mode: SEND")

        swap_plan = [(token_symbol, args.swap_amount)]
        if token_symbol != "LITVM" and args.litvm_swap_amount > 0:
            swap_plan.append(("LITVM", args.litvm_swap_amount))
        random.shuffle(swap_plan)
        log.info("Swap order: %s", " -> ".join(symbol for symbol, _ in swap_plan))
        for symbol, amount in swap_plan:
            nonce = swap_native_to_token(w3, account, router, symbol, to_wei(amount), nonce, args, log)
            sleep_between_actions(log)

        if args.liquidity_amount > 0:
            nonce = add_liquidity_litvm(w3, account, router, to_wei(args.liquidity_amount), nonce, args, log)
            sleep_between_actions(log)

        nonce = stake_litvm(w3, account, farm, args.stake_pct, nonce, log)
        sleep_between_actions(log)

        nonce = casino_coinflip(w3, account, casino, to_wei(args.casino_bet), nonce, log)
        log.info("WolfDex actions completed")
        return 0
    except Exception as exc:  # noqa: BLE001
        log.exception("Fatal error: %s", exc)
        return 1
    finally:
        log.info("Log saved to: %s", log_file)


if __name__ == "__main__":
    sys.exit(main())
