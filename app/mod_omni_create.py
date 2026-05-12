"""
OmniFun — bonding-curve coin creation with ABI variant fallback.
"""
import logging
import random
import string
from web3 import Web3
from web3.exceptions import ContractLogicError

import config

log = logging.getLogger("omni-create")

OMNI_CREATE_VARIANTS = [
    {
        "name": "createCoin(name,symbol,metadata)",
        "abi": [{
            "name": "createCoin", "type": "function", "stateMutability": "payable",
            "inputs": [
                {"name": "name",     "type": "string"},
                {"name": "symbol",   "type": "string"},
                {"name": "metadata", "type": "string"},
            ],
            "outputs": [{"name": "coin", "type": "address"}],
        }],
        "build": lambda c, name, sym, meta, buy=None: c.functions.createCoin(name, sym, meta),
    },
    {
        "name": "create(name,symbol,uri)",
        "abi": [{
            "name": "create", "type": "function", "stateMutability": "payable",
            "inputs": [
                {"name": "name",   "type": "string"},
                {"name": "symbol", "type": "string"},
                {"name": "uri",    "type": "string"},
            ],
            "outputs": [{"name": "coin", "type": "address"}],
        }],
        "build": lambda c, name, sym, meta, buy=None: c.functions.create(name, sym, meta),
    },
    {
        "name": "deployCurve(name,symbol,initialBuy)",
        "abi": [{
            "name": "deployCurve", "type": "function", "stateMutability": "payable",
            "inputs": [
                {"name": "name",       "type": "string"},
                {"name": "symbol",     "type": "string"},
                {"name": "initialBuy", "type": "uint256"},
            ],
            "outputs": [{"name": "coin", "type": "address"}],
        }],
        "build": lambda c, name, sym, meta, buy=0: c.functions.deployCurve(name, sym, buy or 0),
    },
    {
        "name": "launch(name,symbol,description,imageUrl)",
        "abi": [{
            "name": "launch", "type": "function", "stateMutability": "payable",
            "inputs": [
                {"name": "name",        "type": "string"},
                {"name": "symbol",      "type": "string"},
                {"name": "description", "type": "string"},
                {"name": "imageUrl",    "type": "string"},
            ],
            "outputs": [{"name": "coin", "type": "address"}],
        }],
        "build": lambda c, name, sym, meta, buy=None: c.functions.launch(
            name, sym, "auto-launched", meta
        ),
    },
]


def _random_coin():
    themes = ["pepe", "doge", "shiba", "wojak", "chad", "moon", "frog", "cat"]
    word   = random.choice(themes).capitalize()
    suffix = random.choice(["Inu", "AI", "2.0", "Classic", "Fork", ""])
    name   = (word + " " + suffix).strip() or word
    symbol = "".join(random.choices(string.ascii_uppercase, k=random.randint(3, 5)))
    return name, symbol


def run(w3, tx, initial_buy_wei: int = 0):
    if not config.ENABLE_OMNI_CREATE:
        return
    if config.OMNI_FACTORY == "0x" + "0" * 40:
        log.warning("OMNI_FACTORY not set — skipping")
        return

    me   = tx.account.address
    addr = Web3.to_checksum_address(config.OMNI_FACTORY)
    name, sym = _random_coin()

    # Use user-provided metadata URI. If empty, pass a safe placeholder —
    # some contracts require non-empty strings.
    meta = config.OMNI_METADATA_URI or "ipfs://placeholder"

    variants = OMNI_CREATE_VARIANTS
    if getattr(config, "OMNI_CREATE_VARIANT_INDEX", None) is not None:
        variants = [OMNI_CREATE_VARIANTS[config.OMNI_CREATE_VARIANT_INDEX]]

    last_err = None
    for v in variants:
        try:
            c = w3.eth.contract(address=addr, abi=v["abi"])
            call = v["build"](c, name, sym, meta, buy=initial_buy_wei)
            txd = call.build_transaction({"from": me, "value": initial_buy_wei})
            log.info("[omni-create] trying %s  (%s %s)", v["name"], sym, name)
            tx.send(txd, label=f"omni-create:{v['name']}")
            tx.sleep_random()
            log.info("[omni-create] SUCCESS with variant: %s", v["name"])
            log.info("[omni-create] pin in config.py: OMNI_CREATE_VARIANT_INDEX = %d",
                     OMNI_CREATE_VARIANTS.index(v))
            return
        except (ContractLogicError, RuntimeError, ValueError) as e:
            log.warning("[omni-create] variant %s failed: %s", v["name"], str(e)[:150])
            last_err = e
            continue

    raise RuntimeError(f"all Omni-create ABI variants failed; last: {last_err}")
