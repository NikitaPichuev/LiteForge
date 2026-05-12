"""
Reusable helpers: ERC20 approvals, wrap/unwrap zkLTC.
"""
import time
import logging
from web3 import Web3
from abi import ERC20_ABI

log = logging.getLogger("helpers")

MAX_UINT = 2**256 - 1


def erc20(w3: Web3, token_addr: str):
    return w3.eth.contract(address=Web3.to_checksum_address(token_addr), abi=ERC20_ABI)


def symbol(w3, token_addr) -> str:
    try:
        return erc20(w3, token_addr).functions.symbol().call()
    except Exception:
        return token_addr[:8]


def decimals(w3, token_addr) -> int:
    try:
        return erc20(w3, token_addr).functions.decimals().call()
    except Exception:
        return 18


def balance(w3, token_addr, owner) -> int:
    return erc20(w3, token_addr).functions.balanceOf(owner).call()


def ensure_allowance(w3, tx, token_addr: str, spender: str, amount: int):
    """Check allowance; if insufficient, approve max."""
    token  = erc20(w3, token_addr)
    owner  = tx.account.address
    spender = Web3.to_checksum_address(spender)
    current = token.functions.allowance(owner, spender).call()
    if current >= amount:
        log.info("[approve] %s → %s already sufficient (%d)",
                 symbol(w3, token_addr), spender[:10], current)
        return
    log.info("[approve] %s → %s", symbol(w3, token_addr), spender[:10])
    call = token.functions.approve(spender, MAX_UINT)
    tx.send(call.build_transaction({"from": owner}), label=f"approve-{symbol(w3, token_addr)}")
    tx.sleep_random()


def wrap_zkltc(w3, tx, wzkltc_addr: str, amount_wei: int):
    """Wrap native zkLTC → WzkLTC via deposit()."""
    token = erc20(w3, wzkltc_addr)
    call  = token.functions.deposit()
    txd   = call.build_transaction({
        "from":  tx.account.address,
        "value": amount_wei,
    })
    tx.send(txd, label="wrap-zkLTC")
    tx.sleep_random()


def deadline(seconds: int = 600) -> int:
    return int(time.time()) + seconds
