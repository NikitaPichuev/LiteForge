"""
Real ZNS Arc NFT collection deployer with AI-style field generation.
"""
from __future__ import annotations

import argparse
import logging
import pathlib
import random
import re
import sys
from datetime import datetime

from eth_account import Account
from web3 import Web3
from web3.logs import DISCARD

from key_utils import read_private_key as read_selected_private_key


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
KEYS_FILE = PROJECT_ROOT / "keys.txt"

ARC_CHAIN_ID = 5042002
ARC_RPC = "https://rpc.quicknode.testnet.arc.network"
ARC_RPCS = [
    "https://rpc.quicknode.testnet.arc.network",
    "https://rpc.testnet.arc.network",
    "https://rpc.blockdaemon.testnet.arc.network",
    "https://rpc.drpc.testnet.arc.network",
]

LAUNCHPAD_FACTORY = Web3.to_checksum_address("0xf518778a68c0646b8d52ccfe6440ec3b0faddb1b")
ARC_EXPLORER = "https://testnet.arcscan.app"

LAUNCHPAD_ABI = [
    {
        "type": "function",
        "name": "calculateMintFee",
        "stateMutability": "view",
        "inputs": [{"name": "mintPrice", "type": "uint256"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "create",
        "stateMutability": "payable",
        "inputs": [
            {
                "name": "_params",
                "type": "tuple",
                "components": [
                    {"name": "name", "type": "string"},
                    {"name": "symbol", "type": "string"},
                    {"name": "description", "type": "string"},
                    {"name": "imageURI", "type": "string"},
                    {"name": "maxSupply", "type": "uint256"},
                    {"name": "royaltyBps", "type": "uint96"},
                    {"name": "soulbound", "type": "bool"},
                    {
                        "name": "phases",
                        "type": "tuple[]",
                        "components": [
                            {"name": "name", "type": "string"},
                            {"name": "mintPrice", "type": "uint256"},
                            {"name": "startTime", "type": "uint256"},
                            {"name": "endTime", "type": "uint256"},
                            {"name": "maxPerWallet", "type": "uint256"},
                        ],
                    },
                ],
            }
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "createFee",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "minMintFee",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "totalCollections",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "getUserCollections",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [
            {
                "type": "tuple[]",
                "components": [
                    {"name": "collection", "type": "address"},
                    {"name": "creator", "type": "address"},
                    {"name": "name", "type": "string"},
                    {"name": "symbol", "type": "string"},
                    {"name": "createdAt", "type": "uint256"},
                ],
            }
        ],
    },
    {
        "type": "event",
        "name": "Created",
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "collection", "type": "address"},
            {"indexed": True, "name": "creator", "type": "address"},
        ],
    },
]


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"zns_arc_create_nft_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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
    parser = argparse.ArgumentParser(description="Deploy ZNS AI NFT collection on Arc")
    parser.add_argument("--theme", default="arc dream", help="short theme or idea for AI generation")
    parser.add_argument("--name", default=None, help="override collection name")
    parser.add_argument("--symbol", default=None, help="override collection symbol")
    parser.add_argument("--description", default=None, help="override collection description")
    parser.add_argument("--max-supply", type=int, default=999, help="collection max supply")
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

    log.info("Create tx sent: %s", tx_hash.hex())
    receipt = send_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    log.info("Receipt status: %s", receipt.status)
    log.info("Block: %s", receipt.blockNumber)
    log.info("Gas used: %s", receipt.gasUsed)
    if receipt.status != 1:
        raise RuntimeError(f"Create NFT reverted: {tx_hash.hex()}")
    return tx_hash.hex(), receipt


def estimate_gas_with_fallback(tx: dict):
    last_error = None
    for rpc_url in ARC_RPCS:
        try:
            probe_w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
            if not probe_w3.is_connected():
                continue
            if probe_w3.eth.chain_id != ARC_CHAIN_ID:
                continue
            gas = probe_w3.eth.estimate_gas(tx)
            return probe_w3, gas
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    raise RuntimeError(f"Gas estimate failed on all Arc RPCs: {last_error}")


def normalize_theme(theme: str) -> str:
    clean = re.sub(r"\s+", " ", theme.strip())
    return clean or "arc dream"


def build_symbol(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text.upper())
    if not words:
        return "ARCNFT"
    if len(words) >= 2:
        symbol = "".join(word[0] for word in words[:5])
    else:
        symbol = words[0][:6]
    symbol = re.sub(r"[^A-Z0-9]", "", symbol)[:8]
    return symbol or "ARCNFT"


def generate_ai_fields(theme: str) -> tuple[str, str, str]:
    theme = normalize_theme(theme)
    seed = theme.lower()
    rng = random.Random(seed)

    prefixes = [
        "Ethereal",
        "Neon",
        "Luminous",
        "Primal",
        "Silent",
        "Astral",
        "Arc",
        "Velvet",
        "Digital",
        "Chromatic",
        "Solar",
        "Midnight",
    ]
    suffixes = [
        "Dreams",
        "Echoes",
        "Relics",
        "Signals",
        "Fragments",
        "Visions",
        "Mirage",
        "Bloom",
        "Pulse",
        "Archive",
        "Legends",
        "Canvas",
    ]

    theme_words = [w.capitalize() for w in re.findall(r"[A-Za-z0-9]+", theme)]
    primary = " ".join(theme_words[:2]).strip()
    prefix = rng.choice(prefixes)
    suffix = rng.choice(suffixes)

    if primary:
        name = f"{prefix} {primary}"
    else:
        name = f"{prefix} {suffix}"

    if len(theme_words) >= 1 and rng.random() > 0.45:
        name = f"{theme_words[0]} {suffix}"

    name = re.sub(r"\s+", " ", name).strip()[:40]
    symbol = build_symbol(name)
    description = (
        f"AI-crafted NFT collection built around {theme}. "
        "Designed for Arc Testnet with a clean free-mint launch and collectible on-chain identity."
    )
    return name, symbol, description


def coerce_collection_info(item) -> dict:
    if isinstance(item, dict):
        return item
    return {
        "collection": item[0],
        "creator": item[1],
        "name": item[2],
        "symbol": item[3],
        "createdAt": item[4],
    }


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("zns_arc_create_nft")

    if not args.send:
        log.error("This script is for real NFT deploys. Add --send.")
        log.info("Log saved to: %s", log_file)
        return 1
    if args.max_supply < 1 or args.max_supply > 100000:
        log.error("Max supply must be in range 1..100000. Got: %s", args.max_supply)
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

    theme = normalize_theme(args.theme)
    ai_name, ai_symbol, ai_description = generate_ai_fields(theme)
    name = (args.name or ai_name).strip()
    symbol = (args.symbol or ai_symbol).strip().upper()
    description = (args.description or ai_description).strip()

    contract = w3.eth.contract(address=LAUNCHPAD_FACTORY, abi=LAUNCHPAD_ABI)
    create_fee = contract.functions.createFee().call()
    min_mint_fee = contract.functions.minMintFee().call()
    calc_free_mint_fee = contract.functions.calculateMintFee(0).call()
    total_before = contract.functions.totalCollections().call()
    collections_before = [
        coerce_collection_info(item)
        for item in contract.functions.getUserCollections(account.address).call()
    ]

    params = (
        name,
        symbol,
        description,
        "",
        args.max_supply,
        0,
        False,
        [("Public Mint", 0, 0, 0, 0)],
    )

    balance = w3.eth.get_balance(account.address)
    if balance < create_fee:
        log.error("Not enough ARC for create fee: need %s, have %s", create_fee, balance)
        log.info("Log saved to: %s", log_file)
        return 1

    nonce = w3.eth.get_transaction_count(account.address, "pending")
    tx = contract.functions.create(params).build_transaction(
        {
            "from": account.address,
            "chainId": ARC_CHAIN_ID,
            "nonce": nonce,
            "value": create_fee,
            "gas": 1,
            "maxFeePerGas": w3.eth.gas_price,
            "maxPriorityFeePerGas": 0,
        }
    )
    estimate_tx = dict(tx)
    estimate_tx.pop("gas", None)
    try:
        gas_w3, gas = estimate_gas_with_fallback(estimate_tx)
    except RuntimeError as exc:
        log.error("Gas estimate failed: %s", exc)
        log.info("Log saved to: %s", log_file)
        return 1
    tx["gas"] = int(gas * 1.2)
    tx = build_fee_fields(gas_w3, tx)

    total_required = tx["value"] + tx["gas"] * tx["maxFeePerGas"]
    if balance < total_required:
        log.error("Not enough ARC for deploy: need %s, have %s", total_required, balance)
        log.info("Log saved to: %s", log_file)
        return 1

    log.info("Wallet: %s", account.address)
    log.info("Factory: %s", LAUNCHPAD_FACTORY)
    log.info("Theme: %s", theme)
    log.info("AI name: %s", ai_name)
    log.info("AI symbol: %s", ai_symbol)
    log.info("AI description: %s", ai_description)
    log.info("Collection name used: %s", name)
    log.info("Collection symbol used: %s", symbol)
    log.info("Collection description used: %s", description)
    log.info("Image URI used: <empty>")
    log.info("Max supply: %s", args.max_supply)
    log.info("Mint phase: Public Mint / free")
    log.info("Create fee wei: %s", create_fee)
    log.info("Min mint fee wei: %s", min_mint_fee)
    log.info("Calculated mint fee for free mint wei: %s", calc_free_mint_fee)
    log.info("Collections before: %s", len(collections_before))
    log.info("Total collections before: %s", total_before)
    log.info("Estimated gas: %s", gas)
    log.info("Gas limit used: %s", tx["gas"])
    log.info("Max fee per gas wei: %s", tx["maxFeePerGas"])
    log.info("Max priority fee per gas wei: %s", tx["maxPriorityFeePerGas"])
    log.info("Native value wei: %s", tx["value"])
    log.info("Balance wei: %s", balance)

    tx_hash, receipt = sign_and_send(account, tx, log)

    collection_address = None
    try:
        created_logs = contract.events.Created().process_receipt(receipt, errors=DISCARD)
        if created_logs:
            collection_address = created_logs[0]["args"]["collection"]
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to decode Created event: %s", exc)

    collections_after = [
        coerce_collection_info(item)
        for item in contract.functions.getUserCollections(account.address).call()
    ]
    total_after = contract.functions.totalCollections().call()

    if collection_address is None:
        before_set = {item["collection"].lower() for item in collections_before}
        for item in collections_after:
            if item["collection"].lower() not in before_set:
                collection_address = item["collection"]
                break

    log.info("Collections after: %s", len(collections_after))
    log.info("Total collections after: %s", total_after)
    if collection_address:
        log.info("Collection deployed: %s", collection_address)
        log.info("Collection explorer: %s/address/%s", ARC_EXPLORER, collection_address)
    else:
        log.warning("Collection address was not resolved from receipt or user list")
    log.info("Tx explorer: %s/tx/%s", ARC_EXPLORER, tx_hash)
    log.info("Log saved to: %s", log_file)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        logging.exception("Fatal error: %s", exc)
        sys.exit(1)
