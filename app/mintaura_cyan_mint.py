"""
MintAura Cyan mint via Arc Testnet JSON-RPC.

Default mode is dry-run: it checks the contract, builds the claim transaction
and estimates gas, but does not sign or send. Add --send to broadcast.
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

ARC_RPC = "https://rpc.testnet.arc.network"
ARC_CHAIN_ID = 5042002
CYAN_CONTRACT = Web3.to_checksum_address("0x5cDFcf04883487EB9F80840e8b05391e21B79e8A")
ZERO_ADDRESS = "0x" + "0" * 40
NATIVE_TOKEN_MARKER = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
MAX_UINT256 = 2**256 - 1
ZERO_BYTES32 = "0x" + "0" * 64


CYAN_ABI = [
    {
        "type": "function",
        "name": "totalMinted",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "claimCondition",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [
            {
                "name": "condition",
                "type": "tuple",
                "components": [
                    {"name": "startTimestamp", "type": "uint256"},
                    {"name": "maxClaimableSupply", "type": "uint256"},
                    {"name": "supplyClaimed", "type": "uint256"},
                    {"name": "quantityLimitPerWallet", "type": "uint256"},
                    {"name": "merkleRoot", "type": "bytes32"},
                    {"name": "pricePerToken", "type": "uint256"},
                    {"name": "currency", "type": "address"},
                    {"name": "metadata", "type": "string"},
                ],
            }
        ],
    },
    {
        "type": "function",
        "name": "getActiveClaimConditionId",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "getClaimConditionById",
        "stateMutability": "view",
        "inputs": [{"name": "_conditionId", "type": "uint256"}],
        "outputs": [
            {
                "name": "condition",
                "type": "tuple",
                "components": [
                    {"name": "startTimestamp", "type": "uint256"},
                    {"name": "maxClaimableSupply", "type": "uint256"},
                    {"name": "supplyClaimed", "type": "uint256"},
                    {"name": "quantityLimitPerWallet", "type": "uint256"},
                    {"name": "merkleRoot", "type": "bytes32"},
                    {"name": "pricePerToken", "type": "uint256"},
                    {"name": "currency", "type": "address"},
                    {"name": "metadata", "type": "string"},
                ],
            }
        ],
    },
    {
        "type": "function",
        "name": "claim",
        "stateMutability": "payable",
        "inputs": [
            {"name": "receiver", "type": "address"},
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
]


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"mintaura_cyan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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


def condition_to_dict(condition) -> dict:
    names = [
        "startTimestamp",
        "maxClaimableSupply",
        "supplyClaimed",
        "quantityLimitPerWallet",
        "merkleRoot",
        "pricePerToken",
        "currency",
        "metadata",
    ]
    return dict(zip(names, condition))


def get_active_condition(contract) -> dict:
    try:
        condition_id = contract.functions.getActiveClaimConditionId().call()
        condition = contract.functions.getClaimConditionById(condition_id).call()
        return condition_to_dict(condition)
    except Exception:
        condition = contract.functions.claimCondition().call()
        return condition_to_dict(condition)


def is_native_currency(address: str) -> bool:
    return address.lower() in {ZERO_ADDRESS, NATIVE_TOKEN_MARKER}


def parse_args():
    parser = argparse.ArgumentParser(description="Mint MintAura Cyan NFT via API/RPC")
    parser.add_argument("--quantity", type=int, default=1, help="NFT quantity, 1..50")
    parser.add_argument("--send", action="store_true", help="sign and broadcast transaction")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("mintaura")

    if args.quantity < 1 or args.quantity > 50:
        log.error("Quantity must be between 1 and 50.")
        return 1

    pk = read_private_key()
    account = Account.from_key(pk)
    log.info("Wallet: %s", account.address)
    log.info("Contract: %s", CYAN_CONTRACT)
    log.info("Quantity: %d", args.quantity)
    log.info("Mode: %s", "SEND" if args.send else "DRY-RUN")

    w3 = Web3(Web3.HTTPProvider(ARC_RPC, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        log.error("Cannot connect to RPC: %s", ARC_RPC)
        return 1
    chain_id = w3.eth.chain_id
    if chain_id != ARC_CHAIN_ID:
        log.error("Wrong chain id: got %s, expected %s", chain_id, ARC_CHAIN_ID)
        return 1

    contract = w3.eth.contract(address=CYAN_CONTRACT, abi=CYAN_ABI)
    total_before = contract.functions.totalMinted().call()
    condition = get_active_condition(contract)

    log.info("Total minted before: %s", total_before)
    log.info("Claim currency: %s", condition["currency"])
    log.info("Price per NFT wei: %s", condition["pricePerToken"])
    log.info("Claimed in phase: %s", condition["supplyClaimed"])
    log.info("Max supply in phase: %s", condition["maxClaimableSupply"])
    log.info("Wallet limit in phase: %s", condition["quantityLimitPerWallet"])
    log.info("Merkle root: %s", condition["merkleRoot"].hex() if hasattr(condition["merkleRoot"], "hex") else condition["merkleRoot"])

    merkle_root = condition["merkleRoot"]
    if hasattr(merkle_root, "hex"):
        merkle_root = "0x" + merkle_root.hex()
    if merkle_root != ZERO_BYTES32:
        log.error("This claim phase uses a non-empty Merkle root. Allowlist proof fetching is not implemented.")
        log.error("Use the website wallet flow or add proof data.")
        return 1

    price = int(condition["pricePerToken"])
    currency = Web3.to_checksum_address(condition["currency"])
    total_price = price * args.quantity
    if not is_native_currency(currency) and total_price > 0:
        log.error("Mint requires ERC20 payment (%s). Approval flow is not implemented.", currency)
        return 1

    allowlist_proof = ([], 0, MAX_UINT256, ZERO_ADDRESS)
    call = contract.functions.claim(
        account.address,
        args.quantity,
        currency,
        price,
        allowlist_proof,
        b"",
    )

    nonce = w3.eth.get_transaction_count(account.address, "pending")
    tx = call.build_transaction(
        {
            "from": account.address,
            "chainId": ARC_CHAIN_ID,
            "nonce": nonce,
            "value": total_price if is_native_currency(currency) else 0,
        }
    )
    gas = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas * 1.2)
    if "maxFeePerGas" in tx or "maxPriorityFeePerGas" in tx:
        tx.pop("gasPrice", None)
        tx.setdefault("maxFeePerGas", w3.eth.gas_price)
        tx.setdefault("maxPriorityFeePerGas", 0)
    else:
        tx["gasPrice"] = w3.eth.gas_price

    log.info("Estimated gas: %s", gas)
    log.info("Gas limit used: %s", tx["gas"])
    if "gasPrice" in tx:
        log.info("Gas price wei: %s", tx["gasPrice"])
    else:
        log.info("Max fee per gas wei: %s", tx.get("maxFeePerGas"))
        log.info("Max priority fee per gas wei: %s", tx.get("maxPriorityFeePerGas"))
    log.info("Native value wei: %s", tx["value"])

    if not args.send:
        log.info("Dry-run complete. Add --send to broadcast.")
        log.info("Log saved to: %s", log_file)
        return 0

    signed = account.sign_transaction(tx)
    raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
    tx_hash = w3.eth.send_raw_transaction(raw_tx)
    log.info("Sent tx: %s", tx_hash.hex())

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    log.info("Receipt status: %s", receipt.status)
    log.info("Block: %s", receipt.blockNumber)
    log.info("Gas used: %s", receipt.gasUsed)
    if receipt.status != 1:
        log.error("Mint transaction reverted: %s", tx_hash.hex())
        log.info("Log saved to: %s", log_file)
        return 1

    total_after = contract.functions.totalMinted().call()
    log.info("Total minted after: %s", total_after)
    log.info("Mint OK: %s", tx_hash.hex())
    log.info("Explorer: https://arc-testnet-explorer.stg.blockchain.circle.com/tx/%s", tx_hash.hex())
    log.info("Log saved to: %s", log_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
