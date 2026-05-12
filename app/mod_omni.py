"""
OmniFun — bonding-curve launchpad / DEX on LitVM.
The "Swap" and "Liquidity" tabs in the UI imply standard AMM functions.
Treating as a Uniswap V2-style router until proven otherwise.
"""
import logging
from web3 import Web3

import config
from abi import UNISWAP_V2_ROUTER_ABI
from helpers import deadline

log = logging.getLogger("omni")


def run(w3, tx, target_token: str):
    """Swap a bit of zkLTC into `target_token` (e.g. Lester or PEPE).

    target_token must be set — paste the token address from the Omni UI or
    from the explorer after doing one manual swap.
    """
    if not config.ENABLE_OMNI:
        return
    if config.OMNI_ROUTER == "0x" + "0" * 40:
        log.warning("OMNI_ROUTER not set — skipping")
        return

    router = w3.eth.contract(
        address=Web3.to_checksum_address(config.OMNI_ROUTER),
        abi=UNISWAP_V2_ROUTER_ABI,
    )
    wzkltc = Web3.to_checksum_address(config.WZKLTC)
    dst    = Web3.to_checksum_address(target_token)
    me     = tx.account.address

    amount_in = Web3.to_wei(config.SWAP_AMOUNT_ZKLTC, "ether")
    path = [wzkltc, dst]
    call = router.functions.swapExactETHForTokens(0, path, me, deadline())
    txd  = call.build_transaction({"from": me, "value": amount_in})
    tx.send(txd, label="omni-swap")
    tx.sleep_random()
