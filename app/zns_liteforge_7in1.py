"""
Real ZNS LiteForge Streak Wars action runner.
"""
from __future__ import annotations

import argparse
import logging
import pathlib
import random
import re
import sys
import time
from datetime import datetime

import requests
from eth_account import Account
from web3 import Web3
from web3.logs import DISCARD

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
LITEFORGE_EXPLORER = "https://liteforge.explorer.caldera.xyz"
ZNS_JOIN_API = "https://zns.bio/api/quests/join"
ZNS_AWARD_XP_API = "https://zns.bio/api/quests/award-xp"
ZNS_CAMPAIGN_SLUG = "litvm"
NONCE_HINT_RE = re.compile(r"(?:state|next nonce)\s*[: ]\s*(\d+)", re.IGNORECASE)

ZERO_ADDRESS = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
GM_CONTRACT = Web3.to_checksum_address("0x780Ae565a4104b3099dAb72d9610656b94F1389F")
DEPLOY_CONTRACT = Web3.to_checksum_address("0x673e15dc75D7a6e2409f310dEE5c6b27E95906D2")
TOKEN_DEPLOYER = Web3.to_checksum_address("0xf518778A68c0646B8D52cCfE6440eC3B0fADdB1b")
LAUNCHPAD_FACTORY = Web3.to_checksum_address("0x8f95ed212F37cDc19f5C0716c24966D9019939Ee")
VOTE_CONTRACT = Web3.to_checksum_address("0x3e048310c04461d932B92085c89d23909BFb40c4")
DOMAIN_REGISTRY = Web3.to_checksum_address("0x1c6C28403400c44D8D351dEaBcF7B1365F96EbF1")

COLLECTION_NAME = "ZNS Badge"
COLLECTION_SYMBOL = "ZNSB"
COLLECTION_DESCRIPTION = "ZNS Connect Badge Collection"
COLLECTION_IMAGE_URI = "ipfs://QmRMfLv3BoGBtT6BFJ3Q7qowPWqVbgnTfJRQdaXppLSmnJ"
COLLECTION_MAX_SUPPLY = 10000
COLLECTION_END_DELAY = 365 * 24 * 60 * 60

CREATED_COLLECTION_NAME = "ZNS Created NFT"
CREATED_COLLECTION_SYMBOL = "ZNSC"
CREATED_COLLECTION_DESCRIPTION = "ZNS generated NFT collection for LiteForge Streak Wars"

TOKEN_NAME = "ZNS Token"
TOKEN_SYMBOL = "ZNS"
TOKEN_SUPPLY = 1_000_000 * 10**18
TOKEN_DECIMALS = 18

DOMAIN_FEE_WEI = 2_000_000_000_000_000
DOMAIN_YEARS = 1
DOMAIN_CREDITS = 0
DOMAIN_RNG = random.SystemRandom()
DOMAIN_PARTS = [
    "ka",
    "zen",
    "tor",
    "vak",
    "mio",
    "sor",
    "nex",
    "rin",
    "fal",
    "dra",
    "vel",
    "nor",
    "pix",
    "lum",
    "trix",
    "vor",
    "sel",
    "jin",
    "oro",
    "kei",
    "mur",
    "xan",
    "vex",
    "talo",
    "sai",
    "bex",
    "luro",
    "fyn",
    "naro",
    "zefi",
    "mexa",
    "raxo",
    "davo",
    "pavo",
]

GM_ABI = [
    {
        "type": "function",
        "name": "fee",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "nextGMTimer",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "nextGNTimer",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "sayGM",
        "stateMutability": "payable",
        "inputs": [{"name": "referral", "type": "address"}],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "sayGN",
        "stateMutability": "payable",
        "inputs": [{"name": "referral", "type": "address"}],
        "outputs": [],
    },
]

DEPLOY_ABI = [
    {
        "type": "function",
        "name": "fee",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "deploy",
        "stateMutability": "payable",
        "inputs": [{"name": "referral", "type": "address"}],
        "outputs": [],
    },
]

TOKEN_DEPLOYER_ABI = [
    {
        "type": "function",
        "name": "fee",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "deployToken",
        "stateMutability": "payable",
        "inputs": [
            {"name": "name", "type": "string"},
            {"name": "symbol", "type": "string"},
            {"name": "supply", "type": "uint256"},
            {"name": "decimals", "type": "uint8"},
        ],
        "outputs": [],
    },
]

LAUNCHPAD_ABI = [
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

COLLECTION_ABI = [
    {
        "type": "function",
        "name": "totalMintCost",
        "stateMutability": "view",
        "inputs": [{"name": "amount", "type": "uint256"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "mint",
        "stateMutability": "payable",
        "inputs": [{"name": "amount", "type": "uint256"}],
        "outputs": [],
    },
]

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
]

DOMAIN_REGISTRY_ABI = [
    {
        "type": "function",
        "name": "registerDomains",
        "stateMutability": "payable",
        "inputs": [
            {"name": "owners", "type": "address[]"},
            {"name": "domainNames", "type": "string[]"},
            {"name": "expiries", "type": "uint256[]"},
            {"name": "referral", "type": "address"},
            {"name": "credits", "type": "uint256"},
        ],
        "outputs": [],
    },
]

ACTION_TYPES = {
    "gm": "say_gm",
    "gn": "say_gn",
    "deploy-token": "deploy_token",
    "deploy-nft": "deploy_nft",
    "deploy-contract": "deploy_contract",
    "create-nft": "create_nft",
    "mint-nft": "mint_nft",
    "mint-domain": "mint_domain",
    "vote": "vote",
}


def setup_logging() -> pathlib.Path:
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"zns_liteforge_7in1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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
    parser = argparse.ArgumentParser(description="Run ZNS LiteForge Streak Wars actions")
    parser.add_argument("--send", action="store_true", help="required: send real transactions")
    return parser.parse_args()


def build_fee_fields(w3: Web3, tx: dict) -> dict:
    tx.pop("gasPrice", None)
    tx["maxFeePerGas"] = w3.eth.gas_price
    tx["maxPriorityFeePerGas"] = 0
    return tx


def get_contract(w3: Web3, address: str, abi: list[dict]):
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)


def get_safe_pending_nonce(address: str, fallback: int | None = None) -> int:
    best_nonce = -1
    last_error = None
    for rpc_url in LITEFORGE_RPCS:
        try:
            probe = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
            if not probe.is_connected() or probe.eth.chain_id != LITEFORGE_CHAIN_ID:
                continue
            best_nonce = max(best_nonce, probe.eth.get_transaction_count(address, "pending"))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if best_nonce < 0:
        if fallback is not None:
            return fallback
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


def sign_and_send(account, tx: dict, log: logging.Logger, step_name: str):
    last_error = None
    current_nonce = tx["nonce"]
    for attempt in range(1, 5):
        safe_nonce = get_safe_pending_nonce(account.address, fallback=current_nonce)
        if safe_nonce > current_nonce:
            log.info("%s nonce adjusted: %s -> %s", step_name, current_nonce, safe_nonce)
            current_nonce = safe_nonce

        send_tx = dict(tx)
        send_tx["nonce"] = current_nonce
        signed = account.sign_transaction(send_tx)
        raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")

        for rpc_url in LITEFORGE_RPCS:
            send_w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
            try:
                if not send_w3.is_connected() or send_w3.eth.chain_id != LITEFORGE_CHAIN_ID:
                    continue
                tx_hash = send_w3.eth.send_raw_transaction(raw_tx)
                if rpc_url != LITEFORGE_RPC:
                    log.info("%s sent through fallback RPC: %s", step_name, rpc_url)
                tx_hash_hex = tx_hash.hex()
                log.info("%s tx sent: %s", step_name, tx_hash_hex)
                receipt = send_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
                log.info("%s receipt status: %s", step_name, receipt.status)
                log.info("%s block: %s", step_name, receipt.blockNumber)
                log.info("%s gas used: %s", step_name, receipt.gasUsed)
                if receipt.status != 1:
                    raise RuntimeError(f"{step_name} reverted: {tx_hash_hex}")
                log.info("%s explorer: %s/tx/%s", step_name, LITEFORGE_EXPLORER, tx_hash_hex)
                return tx_hash_hex, receipt
            except ValueError as exc:
                last_error = exc
                if "nonce too low" in str(exc).lower():
                    hinted_nonce = extract_nonce_hint(exc)
                    current_nonce = max(current_nonce + 1, hinted_nonce or current_nonce + 1)
                    log.warning("%s nonce too low, retry %s with nonce %s: %s", step_name, attempt, current_nonce, exc)
                    break
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                log.warning("%s RPC send failed on %s: %s", step_name, rpc_url, exc)
        time.sleep(1)
    raise RuntimeError(f"{step_name}: all RPC sends failed: {last_error}")


def build_and_send(
    *,
    w3: Web3,
    account,
    nonce: int,
    log: logging.Logger,
    step_name: str,
    contract_fn,
    value: int,
) -> tuple[int, str, object]:
    balance = w3.eth.get_balance(account.address)
    if balance < value:
        raise RuntimeError(f"{step_name}: not enough zkLTC for value, need {value}, have {balance}")

    tx = contract_fn.build_transaction(
        {
            "from": account.address,
            "chainId": LITEFORGE_CHAIN_ID,
            "nonce": nonce,
            "value": value,
            "gas": 1,
        }
    )
    tx.pop("gas", None)
    gas = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas * 1.2)
    tx = build_fee_fields(w3, tx)

    total_required = tx["value"] + tx["gas"] * tx["maxFeePerGas"]
    if balance < total_required:
        raise RuntimeError(f"{step_name}: not enough zkLTC, need {total_required}, have {balance}")

    log.info("%s estimated gas: %s", step_name, gas)
    log.info("%s gas limit used: %s", step_name, tx["gas"])
    log.info("%s max fee per gas wei: %s", step_name, tx["maxFeePerGas"])
    log.info("%s max priority fee per gas wei: %s", step_name, tx["maxPriorityFeePerGas"])
    log.info("%s native value wei: %s", step_name, tx["value"])

    tx_hash, receipt = sign_and_send(account, tx, log, step_name)
    return nonce + 1, tx_hash, receipt


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


def can_run_timer(timer_value: int) -> bool:
    return int(timer_value) <= 0


def make_collection_params(
    *,
    name: str,
    symbol: str,
    description: str,
    image_uri: str,
    max_supply: int,
) -> tuple:
    collection_end = int(time.time()) + COLLECTION_END_DELAY
    return (
        name,
        symbol,
        description,
        image_uri,
        max_supply,
        0,
        False,
        [("Public", 0, 0, collection_end, 0)],
    )


def resolve_created_collection(
    *,
    launchpad_contract,
    receipt,
    before_collections: list[dict],
    account_address: str,
    log: logging.Logger,
) -> str:
    collection_address = None
    try:
        created_logs = launchpad_contract.events.Created().process_receipt(receipt, errors=DISCARD)
        if created_logs:
            collection_address = created_logs[0]["args"]["collection"]
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to decode Created event: %s", exc)

    after_collections = [
        coerce_collection_info(item)
        for item in launchpad_contract.functions.getUserCollections(account_address).call()
    ]
    if collection_address is None:
        before_set = {item["collection"].lower() for item in before_collections}
        for item in after_collections:
            if item["collection"].lower() not in before_set:
                collection_address = item["collection"]
                break
    if collection_address is None:
        raise RuntimeError("Created collection address was not resolved")
    return Web3.to_checksum_address(collection_address)


def make_domain_name(address: str) -> str:
    _ = address
    for _attempt in range(20):
        part_count = DOMAIN_RNG.randint(3, 5)
        label = "".join(DOMAIN_RNG.choice(DOMAIN_PARTS) for _ in range(part_count))
        label += "".join(str(DOMAIN_RNG.randint(0, 9)) for _ in range(DOMAIN_RNG.randint(1, 3)))
        label = label[:24]
        if 10 <= len(label) <= 24 and not label.startswith(("lit", "lite")):
            return label
    return f"{DOMAIN_RNG.choice(DOMAIN_PARTS)}{DOMAIN_RNG.choice(DOMAIN_PARTS)}{DOMAIN_RNG.randint(1000, 9999)}"[:24]


def sleep_between_actions(log: logging.Logger) -> None:
    delay = random.uniform(2, 5)
    log.info("Pause between actions: %.1fs", delay)
    time.sleep(delay)


def join_litvm_campaign(address: str, log: logging.Logger) -> None:
    payload = {
        "walletAddress": address,
        "campaignSlug": ZNS_CAMPAIGN_SLUG,
    }
    log.info("Quest join API: %s", ZNS_JOIN_API)
    log.info("Quest campaign: %s", ZNS_CAMPAIGN_SLUG)
    response = requests.post(ZNS_JOIN_API, json=payload, timeout=30)
    log.info("Quest join HTTP status: %s", response.status_code)
    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text[:500]}
    log.info("Quest join response: %s", data)

    if response.status_code != 200 or not data.get("success"):
        raise RuntimeError(f"Quest join failed: HTTP {response.status_code} {data}")
    if data.get("alreadyJoined"):
        log.info("Quest join status: already joined")
    else:
        log.info("Quest join status: joined")


def award_quest_xp(action_id: str, address: str, tx_hash: str | None, log: logging.Logger) -> None:
    action_type = ACTION_TYPES.get(action_id, action_id)
    payload = {
        "walletAddress": address,
        "actionType": action_type,
        "txHash": tx_hash,
        "projectSlug": ZNS_CAMPAIGN_SLUG,
    }
    try:
        response = requests.post(ZNS_AWARD_XP_API, json=payload, timeout=30)
        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text[:500]}
        log.info("Quest XP %s HTTP status: %s", action_type, response.status_code)
        log.info("Quest XP %s response: %s", action_type, data)
    except Exception as exc:  # noqa: BLE001
        log.warning("Quest XP %s request failed: %s", action_type, exc)


def main() -> int:
    args = parse_args()
    log_file = setup_logging()
    log = logging.getLogger("zns_liteforge_7in1")

    if not args.send:
        log.error("This script is for real ZNS deploys. Add --send.")
        log.info("Log saved to: %s", log_file)
        return 1

    pk = read_private_key()
    account = Account.from_key(pk)
    join_litvm_campaign(account.address, log)

    w3 = Web3(Web3.HTTPProvider(LITEFORGE_RPC, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        log.error("Cannot connect to LiteForge RPC: %s", LITEFORGE_RPC)
        log.info("Log saved to: %s", log_file)
        return 1
    if w3.eth.chain_id != LITEFORGE_CHAIN_ID:
        log.error("Wrong chain id: got %s, expected %s", w3.eth.chain_id, LITEFORGE_CHAIN_ID)
        log.info("Log saved to: %s", log_file)
        return 1

    gm_contract = get_contract(w3, GM_CONTRACT, GM_ABI)
    deploy_contract = get_contract(w3, DEPLOY_CONTRACT, DEPLOY_ABI)
    token_contract = get_contract(w3, TOKEN_DEPLOYER, TOKEN_DEPLOYER_ABI)
    launchpad_contract = get_contract(w3, LAUNCHPAD_FACTORY, LAUNCHPAD_ABI)
    vote_contract = get_contract(w3, VOTE_CONTRACT, VOTE_ABI)
    domain_registry = get_contract(w3, DOMAIN_REGISTRY, DOMAIN_REGISTRY_ABI)

    gm_fee = gm_contract.functions.fee().call()
    deploy_fee = deploy_contract.functions.fee().call()
    token_fee = token_contract.functions.fee().call()
    create_fee = launchpad_contract.functions.createFee().call()
    min_mint_fee = launchpad_contract.functions.minMintFee().call()
    vote_fee = vote_contract.functions.fee().call()
    next_gm = gm_contract.functions.nextGMTimer(account.address).call()
    next_gn = gm_contract.functions.nextGNTimer(account.address).call()
    user_collections_before = [
        coerce_collection_info(item)
        for item in launchpad_contract.functions.getUserCollections(account.address).call()
    ]

    log.info("Wallet: %s", account.address)
    log.info("Chain id: %s", LITEFORGE_CHAIN_ID)
    log.info("RPC: %s", LITEFORGE_RPC)
    log.info("Referral used: %s", ZERO_ADDRESS)
    log.info("GM contract: %s", GM_CONTRACT)
    log.info("Deploy contract: %s", DEPLOY_CONTRACT)
    log.info("Token deployer: %s", TOKEN_DEPLOYER)
    log.info("Launchpad factory: %s", LAUNCHPAD_FACTORY)
    log.info("Vote contract: %s", VOTE_CONTRACT)
    log.info("Domain registry: %s", DOMAIN_REGISTRY)
    log.info("GM fee wei: %s", gm_fee)
    log.info("Deploy fee wei: %s", deploy_fee)
    log.info("Deploy token fee wei: %s", token_fee)
    log.info("Create collection fee wei: %s", create_fee)
    log.info("Min mint fee wei: %s", min_mint_fee)
    log.info("Vote fee wei: %s", vote_fee)
    log.info("Domain fee wei: %s", DOMAIN_FEE_WEI)
    log.info("nextGMTimer: %s", next_gm)
    log.info("nextGNTimer: %s", next_gn)
    log.info("Collections before: %s", len(user_collections_before))

    nonce = get_safe_pending_nonce(account.address)
    step_results: list[str] = []
    deploy_nft_collection: str | None = None
    created_collection: str | None = None

    def is_balance_error(exc: Exception) -> bool:
        return "insufficient funds" in str(exc).lower() or "not enough zkltc" in str(exc).lower()

    def record_step_error(result_name: str, exc: Exception) -> None:
        if is_balance_error(exc):
            log.warning("%s skipped: insufficient funds: %s", result_name, exc)
            step_results.append(f"{result_name} SKIPPED: insufficient funds")
        else:
            log.warning("%s failed, continuing: %s", result_name, exc)
            short_error = str(exc).replace("\n", " ")[:220]
            step_results.append(f"{result_name} FAILED: {type(exc).__name__}: {short_error}")

    def run_contract_step(result_name: str, action_id: str, step_name: str, contract_fn, value: int):
        nonlocal nonce
        try:
            nonce, tx_hash, receipt = build_and_send(
                w3=w3,
                account=account,
                nonce=nonce,
                log=log,
                step_name=step_name,
                contract_fn=contract_fn,
                value=value,
            )
        except Exception as exc:  # noqa: BLE001
            record_step_error(result_name, exc)
            return None, None
        step_results.append(f"{result_name} OK: {tx_hash}")
        award_quest_xp(action_id, account.address, tx_hash, log)
        sleep_between_actions(log)
        return tx_hash, receipt

    if can_run_timer(next_gm):
        run_contract_step(
            "sayGM",
            "gm",
            "Step 1/9 sayGM",
            gm_contract.functions.sayGM(ZERO_ADDRESS),
            gm_fee,
        )
    else:
        log.info("Step 1/9 sayGM skipped: timer active, remaining %s seconds", next_gm)
        step_results.append("sayGM SKIPPED: timer active")

    if can_run_timer(next_gn):
        run_contract_step(
            "sayGN",
            "gn",
            "Step 2/9 sayGN",
            gm_contract.functions.sayGN(ZERO_ADDRESS),
            gm_fee,
        )
    else:
        log.info("Step 2/9 sayGN skipped: timer active, remaining %s seconds", next_gn)
        step_results.append("sayGN SKIPPED: timer active")

    domain_name = make_domain_name(account.address)
    log.info("Domain name used: %s.lit", domain_name)
    run_contract_step(
        "mintDomain",
        "mint-domain",
        "Step 3/9 mintDomain",
        domain_registry.functions.registerDomains(
            [account.address],
            [domain_name],
            [DOMAIN_YEARS],
            ZERO_ADDRESS,
            DOMAIN_CREDITS,
        ),
        DOMAIN_FEE_WEI,
    )

    deploy_nft_params = make_collection_params(
        name=COLLECTION_NAME,
        symbol=COLLECTION_SYMBOL,
        description=COLLECTION_DESCRIPTION,
        image_uri=COLLECTION_IMAGE_URI,
        max_supply=COLLECTION_MAX_SUPPLY,
    )
    before_deploy_nft = [
        coerce_collection_info(item)
        for item in launchpad_contract.functions.getUserCollections(account.address).call()
    ]
    _, deploy_nft_receipt = run_contract_step(
        "deployNFT",
        "deploy-nft",
        "Step 4/9 deployNFT",
        launchpad_contract.functions.create(deploy_nft_params),
        create_fee,
    )
    if deploy_nft_receipt is not None:
        try:
            deploy_nft_collection = resolve_created_collection(
                launchpad_contract=launchpad_contract,
                receipt=deploy_nft_receipt,
                before_collections=before_deploy_nft,
                account_address=account.address,
                log=log,
            )
            log.info("Deploy NFT collection: %s", deploy_nft_collection)
            log.info("Deploy NFT collection explorer: %s/address/%s", LITEFORGE_EXPLORER, deploy_nft_collection)
        except Exception as exc:  # noqa: BLE001
            record_step_error("deployNFT resolve", exc)

    run_contract_step(
        "deployToken",
        "deploy-token",
        "Step 5/9 deployToken",
        token_contract.functions.deployToken(
            TOKEN_NAME,
            TOKEN_SYMBOL,
            TOKEN_SUPPLY,
            TOKEN_DECIMALS,
        ),
        token_fee,
    )

    run_contract_step(
        "deployContract",
        "deploy-contract",
        "Step 6/9 deployContract",
        deploy_contract.functions.deploy(ZERO_ADDRESS),
        deploy_fee,
    )

    create_params = make_collection_params(
        name=CREATED_COLLECTION_NAME,
        symbol=CREATED_COLLECTION_SYMBOL,
        description=CREATED_COLLECTION_DESCRIPTION,
        image_uri=COLLECTION_IMAGE_URI,
        max_supply=COLLECTION_MAX_SUPPLY,
    )
    before_create_nft = [
        coerce_collection_info(item)
        for item in launchpad_contract.functions.getUserCollections(account.address).call()
    ]
    _, create_receipt = run_contract_step(
        "createNFT",
        "create-nft",
        "Step 7/9 createNFT",
        launchpad_contract.functions.create(create_params),
        create_fee,
    )
    if create_receipt is not None:
        try:
            created_collection = resolve_created_collection(
                launchpad_contract=launchpad_contract,
                receipt=create_receipt,
                before_collections=before_create_nft,
                account_address=account.address,
                log=log,
            )
            log.info("Created collection: %s", created_collection)
            log.info("Created collection explorer: %s/address/%s", LITEFORGE_EXPLORER, created_collection)
        except Exception as exc:  # noqa: BLE001
            record_step_error("createNFT resolve", exc)

    collection_to_mint = created_collection or deploy_nft_collection
    if collection_to_mint is None:
        log.warning("mintNFT skipped: no created collection available")
        step_results.append("mintNFT SKIPPED: no collection")
    else:
        minted_collection = get_contract(w3, collection_to_mint, COLLECTION_ABI)
        try:
            mint_cost = minted_collection.functions.totalMintCost(1).call()
        except Exception as exc:  # noqa: BLE001
            log.warning("totalMintCost(1) failed, fallback to minMintFee: %s", exc)
            mint_cost = min_mint_fee
        log.info("Mint collection used: %s", collection_to_mint)
        log.info("Mint cost wei used: %s", mint_cost)
        run_contract_step(
            "mintNFT",
            "mint-nft",
            "Step 8/9 mintNFT",
            minted_collection.functions.mint(1),
            mint_cost,
        )

    run_contract_step(
        "vote",
        "vote",
        "Step 9/9 vote",
        vote_contract.functions.vote(ZERO_ADDRESS),
        vote_fee,
    )

    log.info("9 actions completed")
    for line in step_results:
        log.info("Result: %s", line)
    log.info("Log saved to: %s", log_file)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        logging.exception("Fatal error: %s", exc)
        sys.exit(1)
