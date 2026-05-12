"""
LitVM LiteForge interaction bot — config.

Fill in contract addresses by doing ONE manual transaction in each dApp
and copying the "To" address from MetaMask or from the tx details in
https://liteforge.explorer.caldera.xyz/
"""

# ---------- Network ----------
RPC_HTTP = "https://liteforge.rpc.caldera.xyz/http"
RPC_WS   = "wss://liteforge.rpc.caldera.xyz/ws"
CHAIN_ID = 4441
EXPLORER = "https://liteforge.explorer.caldera.xyz"

# Native gas token = zkLTC (no ERC-20 address, sent as tx.value)

# ---------- Proxy (optional) ----------
# PREFERRED: put proxy in proxies.txt (one per line).
# Supported formats there: http://user:pass@host:port, socks5://..., host:port:user:pass, host:port
# This value is used ONLY if proxies.txt is empty or missing.
PROXY = None

# ---------- Private key ----------
# PREFERRED: put key in keys.txt (one per line, with or without 0x).
# Fallback: set environment variable PRIVATE_KEY before running.
# NEVER hardcode the key in this file.

# ---------- Gas ----------
GAS_MULTIPLIER    = 1.2      # safety margin on estimate
MAX_FEE_GWEI      = 2.0      # cap in case RPC returns silly values
PRIORITY_FEE_GWEI = 0.01     # Caldera chains usually take tiny tips

# ---------- Contract addresses (FILL THESE IN) ----------
# How to get: open the dApp, do ONE approve or swap manually, then open
# the tx in the explorer. The "Interacted With" / "To" address is the
# router/pool you need. For token addresses, open the "Tokens" tab of
# the tx and copy addresses of transferred ERC-20s.

# ---- LiteSwap (Uniswap V2-style DEX) ----
LITESWAP_ROUTER  = "0x0000000000000000000000000000000000000000"  # TODO
LITESWAP_FACTORY = "0x0000000000000000000000000000000000000000"  # optional
LITESWAP_STAKING = "0x0000000000000000000000000000000000000000"  # TODO (LP staking)

# ---- OmniFun (bonding-curve launchpad / DEX) ----
OMNI_ROUTER = "0x0000000000000000000000000000000000000000"  # TODO
OMNI_TARGET_TOKEN = "0x0000000000000000000000000000000000000000"  # TODO: token to buy on Omni

# ---- Aynilabs (Aave V3-style lending) ----
AYNI_POOL    = "0x0000000000000000000000000000000000000000"  # TODO — main Pool contract
AYNI_WZKLTC_GATEWAY = "0x0000000000000000000000000000000000000000"  # TODO — WzkLTC wrapping helper (if any)

# ---- Lester Labs (token factory) ----
LESTER_FACTORY = "0x93acc61fcdc2e3407A0c03450Adfd8aE78964948"
LESTER_DEPLOY_FEE_ZKLTC = 0.05

# ---- OmniFun (coin creation factory on bonding curve) ----
OMNI_FACTORY = "0x0000000000000000000000000000000000000000"  # TODO

# ---- Tokens ----
# Native zkLTC is wrapped to WzkLTC for DEX routing (standard pattern)
WZKLTC = "0x0000000000000000000000000000000000000000"  # TODO
USDC   = "0xd5118dEe968d1533B2A57aB66C266010AD8957fa"

# ---------- Strategy ----------
# Enable / disable individual modules
ENABLE_LITESWAP     = True
ENABLE_OMNI         = True
ENABLE_AYNI         = True
ENABLE_LESTER       = True
ENABLE_OMNI_CREATE  = True

# Amounts (in human units, converted to wei inside the script)
SWAP_AMOUNT_ZKLTC   = 0.01    # per swap
LP_AMOUNT_ZKLTC     = 0.02    # to add to LP
AYNI_SUPPLY_ZKLTC   = 0.02    # to wrap and supply
AYNI_BORROW_USDC    = 1.0     # borrow amount

# ---------- ABI variant overrides ----------
# After the first successful run the module will print a line like
#   "[lester] pin this in config.py: LESTER_VARIANT_INDEX = 1"
# Set the value here to skip trial-and-error on subsequent runs.
LESTER_VARIANT_INDEX        = None   # 0..3
OMNI_CREATE_VARIANT_INDEX   = None   # 0..3

# ---------- Omni create metadata ----------
# To find a valid URI: open any existing coin on Omni, open it in the
# explorer, call tokenURI() on the token contract. Paste the returned URI
# here. If left empty the code uses "ipfs://placeholder" which will
# probably fail validation on most contracts.
OMNI_METADATA_URI = ""

# Random delay between actions (seconds) to avoid nonce / rate-limit issues
DELAY_MIN = 15
DELAY_MAX = 45
