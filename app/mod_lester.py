"""
Lester Labs — token minter on LitVM.

Factory: 0x93acc61fcdc2e3407A0c03450Adfd8aE78964948
Method:  createToken(string name, string symbol, uint256 totalSupply,
                     uint8 decimals, bool mintable, bool burnable, bool pausable)
Fee:     0.05 zkLTC (payable)
Event:   TokenCreated(address indexed token, address indexed creator)
         topic0 = 0xd5d05a8421149c74fd223cfc823befb883babf9bf0b0e4d6bf9c8fdb70e59bb4
"""
import logging
import random
import string

from web3 import Web3

import config

log = logging.getLogger("lester")

LESTER_ABI = [
    {
        "name": "createToken",
        "type": "function",
        "stateMutability": "payable",
        "inputs": [
            {"name": "name",        "type": "string"},
            {"name": "symbol",      "type": "string"},
            {"name": "totalSupply", "type": "uint256"},
            {"name": "decimals",    "type": "uint8"},
            {"name": "mintable",    "type": "bool"},
            {"name": "burnable",    "type": "bool"},
            {"name": "pausable",    "type": "bool"},
        ],
        "outputs": [{"name": "token", "type": "address"}],
    },
    {
        "name": "TokenCreated",
        "type": "event",
        "anonymous": False,
        "inputs": [
            {"name": "token",   "type": "address", "indexed": True},
            {"name": "creator", "type": "address", "indexed": True},
        ],
    },
]

TOKEN_CREATED_TOPIC = "0xd5d05a8421149c74fd223cfc823befb883babf9bf0b0e4d6bf9c8fdb70e59bb4"


def _random_token_meta():
    prefixes = ["Lite", "Zk", "Forge", "Orbit", "Caldera", "Lit", "Nova", "Pulse"]
    suffixes = ["Coin", "Token", "Cash", "Gold", "Silver", "Dao", "Fi", "X"]
    name = random.choice(prefixes) + random.choice(suffixes)
    symbol = "".join(random.choices(string.ascii_uppercase, k=random.randint(3, 5)))
    supply = random.choice([1_000_000, 10_000_000, 100_000_000, 1_000_000_000])
    return name, symbol, supply


def run(w3, tx):
    if not config.ENABLE_LESTER:
        return
    if config.LESTER_FACTORY == "0x" + "0" * 40:
        log.warning("LESTER_FACTORY not set — skipping")
        return

    addr    = Web3.to_checksum_address(config.LESTER_FACTORY)
    factory = w3.eth.contract(address=addr, abi=LESTER_ABI)
    me      = tx.account.address
    fee_wei = Web3.to_wei(config.LESTER_DEPLOY_FEE_ZKLTC, "ether")

    name, sym, supply = _random_token_meta()
    supply_wei = supply * (10 ** 18)

    log.info("[lester] deploying %s (%s)  supply=%d", name, sym, supply)

    # Randomize the feature flags a little — just to not look like copy-paste
    mintable = False
    burnable = random.choice([True, False])
    pausable = False

    call = factory.functions.createToken(
        name, sym, supply_wei, 18, mintable, burnable, pausable
    )
    txd = call.build_transaction({"from": me, "value": fee_wei})
    txh = tx.send(txd, label="lester-deploy")

    # Find the created token address in the receipt logs
    try:
        rcpt = w3.eth.get_transaction_receipt(txh)
        for lg in rcpt["logs"]:
            if lg["topics"] and lg["topics"][0].hex() == TOKEN_CREATED_TOPIC:
                token_addr = "0x" + lg["topics"][1].hex()[-40:]
                token_addr = Web3.to_checksum_address(token_addr)
                log.info("[lester] created token: %s", token_addr)
                break
    except Exception as e:
        log.warning("[lester] couldn't parse created-token event: %s", e)

    tx.sleep_random()
