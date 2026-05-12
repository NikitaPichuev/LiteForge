"""
LiteSwap (Uniswap V2 fork — most likely).

If on-chain calls revert with "function selector not recognized", open the
router address in the explorer, look at the verified ABI, and adjust
function names here. Typical alternatives: swapExactETHForTokensSupportingFeeOnTransferTokens.
"""
import logging
from web3 import Web3

import config
from abi import UNISWAP_V2_ROUTER_ABI, STAKING_ABI
from helpers import ensure_allowance, deadline, balance, decimals, symbol

log = logging.getLogger("liteswap")


def run(w3, tx):
    if not config.ENABLE_LITESWAP:
        return
    if config.LITESWAP_ROUTER == "0x" + "0" * 40:
        log.warning("LITESWAP_ROUTER not set — skipping")
        return

    router = w3.eth.contract(
        address=Web3.to_checksum_address(config.LITESWAP_ROUTER),
        abi=UNISWAP_V2_ROUTER_ABI,
    )
    wzkltc = Web3.to_checksum_address(config.WZKLTC)
    usdc   = Web3.to_checksum_address(config.USDC)
    me     = tx.account.address

    # 1) Swap native zkLTC -> USDC
    amount_in = Web3.to_wei(config.SWAP_AMOUNT_ZKLTC, "ether")
    path = [wzkltc, usdc]
    try:
        amounts_out = router.functions.getAmountsOut(amount_in, path).call()
        min_out = int(amounts_out[-1] * 0.95)  # 5% slippage
    except Exception as e:
        log.warning("getAmountsOut failed (%s), using 0 min", e)
        min_out = 0

    call = router.functions.swapExactETHForTokens(min_out, path, me, deadline())
    txd  = call.build_transaction({"from": me, "value": amount_in})
    tx.send(txd, label="liteswap-swap")
    tx.sleep_random()

    # 2) Add liquidity zkLTC + USDC
    usdc_dec = decimals(w3, usdc)
    usdc_bal = balance(w3, usdc, me)
    if usdc_bal == 0:
        log.warning("no USDC balance, skipping addLiquidity")
        return

    lp_zkltc = Web3.to_wei(config.LP_AMOUNT_ZKLTC, "ether")
    # Use half of USDC balance for LP pairing
    lp_usdc  = usdc_bal // 2

    ensure_allowance(w3, tx, usdc, config.LITESWAP_ROUTER, lp_usdc)

    call = router.functions.addLiquidityETH(
        usdc, lp_usdc, 0, 0, me, deadline()
    )
    txd = call.build_transaction({"from": me, "value": lp_zkltc})
    tx.send(txd, label="liteswap-addLP")
    tx.sleep_random()

    # 3) Stake LP (if staking contract configured)
    if config.LITESWAP_STAKING != "0x" + "0" * 40:
        # We don't know the LP token address — skip unless you set it.
        # Usually you'd: find LP token from factory.getPair(), approve it to
        # staking contract, then stake full balance.
        log.info("LP staking skipped — needs LP token address + staking ABI check")
