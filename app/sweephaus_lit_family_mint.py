from __future__ import annotations

import argparse
import logging
import os
import pathlib
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime

from eth_account import Account
from web3 import Web3

from key_utils import read_private_key


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"

LITEFORGE_CHAIN_ID = 4441
LITEFORGE_RPCS = [
    os.environ.get("LITEFORGE_RPC_URL", "").strip(),
    os.environ.get("EVM_RPC_URL", "").strip(),
    "https://liteforge.rpc.caldera.xyz/http",
    "https://liteforge.rpc.caldera.xyz/infra-partner-http",
]
LITEFORGE_RPCS = [rpc for rpc in dict.fromkeys(LITEFORGE_RPCS) if rpc]

NATIVE_TOKEN_ADDRESS = Web3.to_checksum_address("0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE")
ZERO_ADDRESS = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
MAX_UINT256 = (1 << 256) - 1
PRICE_WEI = 202_020_202_020_202
TOKEN_ID = 0
NONCE_HINT_RE = re.compile(r"(?:state|next nonce)\s*[: ]\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class SweepCollection:
    key: str
    name: str
    contract: str


COLLECTIONS = [
    SweepCollection(
        key="ms-lit",
        name="Ms. Lit",
        contract="0x53049cae50D90F21Cd9b458dDfbCfA6bb1CA0ba7",
    ),
    SweepCollection(
        key="kid-lit",
        name="Kid. Lit",
        contract="0x978248AfC00C240437376370D7649C6d24423ef5",
    ),
    SweepCollection(
        key="cat-lit",
        name="Cat. Lit",
        contract="0x20d6A65731367D015D7eE1e28643Cb6f817D3eE1",
    ),
]


ERC1155_DROP_ABI = [
    {
        "type": "function",
        "name": "claim",
        "stateMutability": "payable",
        "inputs": [
            {"name": "receiver", "type": "address"},
            {"name": "tokenId", "type": "uint256"},
            {"name": "quantity", "type": "uint256"},
            {"name": "currency", "type": "address"},
            {"name": "pricePerToken", "type": "uint256"},
            {
                "name": "allowlistProof",
                "type": "tuple",
                "components": [
                    {"name": "proof", "type": "bytes32[]"},
                    {"name": "quantityLimitPerWallet", "type": "uint256"},
                    {"name": "pricePerToken", "type": "uint256"},
                    {"name": "currency", "type": "address"},
                ],
            },
            {"name": "data", "type": "bytes"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "id", "type": "uint256"},
        ],
        "outputs": [{"type": "uint256"}],
    },
]


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"sweephaus_lit_family_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mint SweepHaus Lit Family Collection on LiteForge")
    parser.add_argument(
        "--collection",
        default="all",
        choices=["all", "ms-lit", "kid-lit", "cat-lit"],
        help="collection to mint; default: all three",
    )
    parser.add_argument("--quantity", type=int, default=1, help="mint quantity per collection")
    parser.add_argument("--force", action="store_true", help="mint even if wallet already owns tokenId 0")
    parser.add_argument("--send", action="store_true", help="required: send real transactions")
    return parser.parse_args()


def selected_collections(key: str) -> list[SweepCollection]:
    if key == "all":
        return COLLECTIONS
    return [collection for collection in COLLECTIONS if collection.key == key]


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
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("RPC failed %s: %s", rpc, exc)
    raise RuntimeError(f"Cannot connect to LiteForge RPC: {last_error}")


def get_safe_pending_nonce(account_address: str) -> int:
    best_nonce = -1
    last_error = None
    for rpc in LITEFORGE_RPCS:
        try:
            probe_w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
            if not probe_w3.is_connected() or probe_w3.eth.chain_id != LITEFORGE_CHAIN_ID:
                continue
            best_nonce = max(best_nonce, probe_w3.eth.get_transaction_count(account_address, "pending"))
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


def build_fee_fields(w3: Web3, tx: dict) -> dict:
    tx["maxFeePerGas"] = w3.eth.gas_price
    tx["maxPriorityFeePerGas"] = 0
    tx.pop("gasPrice", None)
    return tx


def sign_and_send(account, tx: dict, log: logging.Logger):
    current_nonce = tx["nonce"]
    last_error = None
    tx_hash = None
    send_w3 = None

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
                if not send_w3.is_connected() or send_w3.eth.chain_id != LITEFORGE_CHAIN_ID:
                    continue

                rpc_pending = send_w3.eth.get_transaction_count(account.address, "pending")
                if rpc_pending > send_tx["nonce"]:
                    log.info("Adjusted nonce from RPC %s: %s -> %s", rpc, send_tx["nonce"], rpc_pending)
                    send_tx["nonce"] = rpc_pending
                    current_nonce = rpc_pending

                signed = account.sign_transaction(send_tx)
                raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
                tx_hash = send_w3.eth.send_raw_transaction(raw_tx)
                break
            except ValueError as exc:
                last_error = exc
                if "nonce too low" in str(exc).lower():
                    hinted_nonce = extract_nonce_hint(exc)
                    current_nonce = hinted_nonce if hinted_nonce is not None else current_nonce + 1
                    log.warning("Nonce mismatch, retry with nonce %s", current_nonce)
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

        if tx_hash is not None:
            break
        time.sleep(1 + attempt)

    if tx_hash is None or send_w3 is None:
        raise RuntimeError(f"Transaction send failed: {last_error}")

    hex_hash = tx_hash.hex()
    log.info("Mint tx sent: %s", hex_hash)
    receipt = send_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    log.info("Mint receipt status: %s", receipt.status)
    if receipt.status != 1:
        raise RuntimeError(f"Mint transaction reverted: {hex_hash}")
    return receipt


def mint_collection(w3: Web3, account, collection: SweepCollection, quantity: int, force: bool, send: bool, log: logging.Logger) -> bool:
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(collection.contract),
        abi=ERC1155_DROP_ABI,
    )

    owned = contract.functions.balanceOf(account.address, TOKEN_ID).call()
    if owned > 0 and not force:
        log.info("%s skipped: already owns tokenId %s balance=%s", collection.name, TOKEN_ID, owned)
        return False

    total_value = PRICE_WEI * quantity
    allowlist_proof = ([], 0, MAX_UINT256, ZERO_ADDRESS)
    fn = contract.functions.claim(
        account.address,
        TOKEN_ID,
        quantity,
        NATIVE_TOKEN_ADDRESS,
        PRICE_WEI,
        allowlist_proof,
        b"",
    )

    tx = fn.build_transaction(
        {
            "from": account.address,
            "value": total_value,
            "chainId": LITEFORGE_CHAIN_ID,
            "nonce": get_safe_pending_nonce(account.address),
        }
    )
    tx = build_fee_fields(w3, tx)
    gas = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas * 1.25)

    log.info("Mint %s", collection.name)
    log.info("Contract: %s", Web3.to_checksum_address(collection.contract))
    log.info("Token ID: %s, quantity: %s", TOKEN_ID, quantity)
    log.info("Price per NFT: %s zkLTC", Web3.from_wei(PRICE_WEI, "ether"))
    log.info("Total value: %s zkLTC", Web3.from_wei(total_value, "ether"))
    log.info("Gas estimate: %s, gas limit: %s", gas, tx["gas"])

    if not send:
        log.info("Dry run only. Add --send to broadcast.")
        return False

    sign_and_send(account, tx, log)
    return True


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("sweephaus")

    try:
        if args.quantity < 1 or args.quantity > 50:
            raise RuntimeError("quantity must be 1..50")

        account = Account.from_key(read_private_key())
        log.info("Wallet: %s", account.address)
        log.info("SweepHaus quest: https://sweep.haus/quests/Lit_Family_Collection")
        log.info("Collection mode: %s", args.collection)

        w3 = connect_rpc(log)
        balance = w3.eth.get_balance(account.address)
        log.info("LiteForge balance: %s zkLTC", Web3.from_wei(balance, "ether"))

        minted = 0
        for index, collection in enumerate(selected_collections(args.collection), start=1):
            if index > 1:
                time.sleep(random.uniform(1.5, 3.5))
            if mint_collection(w3, account, collection, args.quantity, args.force, args.send, log):
                minted += 1

        log.info("SweepHaus completed: sent=%s", minted)
        log.info("Log saved to: %s", log_file)
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("Error: %s", exc)
        log.error("Log saved to: %s", log_file)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
