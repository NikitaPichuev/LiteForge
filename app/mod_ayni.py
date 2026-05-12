"""
Aynilabs — lending protocol. Described as Aave-style, assuming Aave V3 fork.

Flow from the guide:
  1) wrap zkLTC → WzkLTC
  2) supply WzkLTC to Pool
  3) borrow USDC
"""
import logging
from web3 import Web3

import config
from abi import AAVE_V3_POOL_ABI
from helpers import ensure_allowance, wrap_zkltc, balance, decimals

log = logging.getLogger("ayni")


def run(w3, tx):
    if not config.ENABLE_AYNI:
        return
    if config.AYNI_POOL == "0x" + "0" * 40:
        log.warning("AYNI_POOL not set — skipping")
        return

    pool = w3.eth.contract(
        address=Web3.to_checksum_address(config.AYNI_POOL),
        abi=AAVE_V3_POOL_ABI,
    )
    wzkltc = Web3.to_checksum_address(config.WZKLTC)
    usdc   = Web3.to_checksum_address(config.USDC)
    me     = tx.account.address

    # 1) Wrap zkLTC -> WzkLTC
    wrap_amount = Web3.to_wei(config.AYNI_SUPPLY_ZKLTC, "ether")
    wrap_zkltc(w3, tx, wzkltc, wrap_amount)

    # 2) Supply WzkLTC
    wbal = balance(w3, wzkltc, me)
    supply_amount = min(wrap_amount, wbal)
    ensure_allowance(w3, tx, wzkltc, config.AYNI_POOL, supply_amount)
    call = pool.functions.supply(wzkltc, supply_amount, me, 0)
    txd  = call.build_transaction({"from": me})
    tx.send(txd, label="ayni-supply")
    tx.sleep_random()

    # 3) Borrow USDC (variable rate)
    usdc_dec = decimals(w3, usdc)
    borrow_amount = int(config.AYNI_BORROW_USDC * (10 ** usdc_dec))
    call = pool.functions.borrow(usdc, borrow_amount, 2, 0, me)
    txd  = call.build_transaction({"from": me})
    tx.send(txd, label="ayni-borrow")
    tx.sleep_random()
