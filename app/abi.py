"""
Minimal ABIs. We include ONLY the functions the bot actually calls.
"""

ERC20_ABI = [
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "owner", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "allowance", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "owner", "type": "address"},
                {"name": "spender", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "approve", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "spender", "type": "address"},
                {"name": "amount",  "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "decimals", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
    {"name": "symbol", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "string"}]},
    # WETH-style wrap/unwrap (WzkLTC likely has these)
    {"name": "deposit", "type": "function", "stateMutability": "payable",
     "inputs": [], "outputs": []},
    {"name": "withdraw", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "wad", "type": "uint256"}], "outputs": []},
]

# Uniswap V2 style router — LiteSwap, OmniFun almost certainly are forks of this
UNISWAP_V2_ROUTER_ABI = [
    {"name": "swapExactETHForTokens", "type": "function", "stateMutability": "payable",
     "inputs": [{"name": "amountOutMin", "type": "uint256"},
                {"name": "path", "type": "address[]"},
                {"name": "to", "type": "address"},
                {"name": "deadline", "type": "uint256"}],
     "outputs": [{"name": "amounts", "type": "uint256[]"}]},
    {"name": "swapExactTokensForETH", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "amountIn", "type": "uint256"},
                {"name": "amountOutMin", "type": "uint256"},
                {"name": "path", "type": "address[]"},
                {"name": "to", "type": "address"},
                {"name": "deadline", "type": "uint256"}],
     "outputs": [{"name": "amounts", "type": "uint256[]"}]},
    {"name": "swapExactTokensForTokens", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "amountIn", "type": "uint256"},
                {"name": "amountOutMin", "type": "uint256"},
                {"name": "path", "type": "address[]"},
                {"name": "to", "type": "address"},
                {"name": "deadline", "type": "uint256"}],
     "outputs": [{"name": "amounts", "type": "uint256[]"}]},
    {"name": "addLiquidityETH", "type": "function", "stateMutability": "payable",
     "inputs": [{"name": "token", "type": "address"},
                {"name": "amountTokenDesired", "type": "uint256"},
                {"name": "amountTokenMin", "type": "uint256"},
                {"name": "amountETHMin", "type": "uint256"},
                {"name": "to", "type": "address"},
                {"name": "deadline", "type": "uint256"}],
     "outputs": [{"name": "amountToken", "type": "uint256"},
                 {"name": "amountETH",   "type": "uint256"},
                 {"name": "liquidity",   "type": "uint256"}]},
    {"name": "getAmountsOut", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "amountIn", "type": "uint256"},
                {"name": "path", "type": "address[]"}],
     "outputs": [{"name": "amounts", "type": "uint256[]"}]},
]

# Aave V3 Pool — Aynilabs is described as lending protocol, most likely Aave v3 fork
AAVE_V3_POOL_ABI = [
    {"name": "supply", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "asset", "type": "address"},
                {"name": "amount", "type": "uint256"},
                {"name": "onBehalfOf", "type": "address"},
                {"name": "referralCode", "type": "uint16"}],
     "outputs": []},
    {"name": "borrow", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "asset", "type": "address"},
                {"name": "amount", "type": "uint256"},
                {"name": "interestRateMode", "type": "uint256"},  # 1=stable, 2=variable
                {"name": "referralCode", "type": "uint16"},
                {"name": "onBehalfOf", "type": "address"}],
     "outputs": []},
    {"name": "withdraw", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "asset", "type": "address"},
                {"name": "amount", "type": "uint256"},
                {"name": "to", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
]

# Generic LP staking (MasterChef-like)
STAKING_ABI = [
    {"name": "deposit", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "pid", "type": "uint256"},
                {"name": "amount", "type": "uint256"}],
     "outputs": []},
    {"name": "stake", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "amount", "type": "uint256"}],
     "outputs": []},
    {"name": "claim", "type": "function", "stateMutability": "nonpayable",
     "inputs": [], "outputs": []},
]
