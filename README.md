# LitVMassasas

Automation toolkit for LiteForge / LitEVM activity.

The main entry point is `menu.bat` on Windows. The menu is configured for real runs: actions that are meant to send transactions are launched with send flags already enabled. Most scripts read wallets from `keys.txt`, run actions one wallet at a time, and write logs to `logs/`.

## Safety

- This repository must not contain real private keys, seed phrases, proxy credentials, logs, or cooldown state.
- Fill your own `keys.txt` locally.
- Many menu actions send real transactions on their configured networks. Read the prompt before running.
- dApp APIs and contracts can change. If a flow starts failing, verify the current website/contract behavior first.

## Requirements

- Windows with PowerShell / Command Prompt.
- Python 3.10+.
- Node.js 18+.
- Network access to the configured RPC/API endpoints.

## Install

1. Clone or unpack this public folder.
2. Create local working files from templates:

```text
copy keys.txt.example keys.txt
copy proxies.txt.example proxies.txt
copy wallet_addresses.txt.example wallet_addresses.txt
copy faucet_addresses.txt.example faucet_addresses.txt
```

3. Put one private key per line in `keys.txt`.
4. Run `menu.bat`.
5. Choose `1. Install dependencies`.

Manual install:

```powershell
python -m pip install -r requirements.txt
npm install
```

## Environment

Common optional variables:

```powershell
$env:PRIVATE_KEY="0x..."
$env:BOT_PRIVATE_KEY="0x..."
$env:KEY_INDEX="1"
$env:EVM_RPC_URL="https://liteforge.rpc.caldera.xyz/http"
$env:EVM_CHAIN_ID="4441"
$env:MIDAS_API_BASE="https://predict-testnet-api.midashand.xyz/api"
```

For multi-wallet runs, prefer `keys.txt`.

## Files

- `menu.bat` - main interactive launcher.
- `app/` - Python and Node.js scripts.
- `keys.txt` - local private keys, one per line. Not included publicly.
- `proxies.txt` - optional proxies. Not included publicly.
- `wallet_addresses.txt` / `faucet_addresses.txt` - optional address lists. Not included publicly.
- `logs/` - generated logs. Not included publicly.
- `state/` - generated local cache files. Not included publicly.

## Main Menu

### 1. Install dependencies

Installs Python packages from `requirements.txt` and Node dependencies from `package.json`.

Use this first after unpacking the project. After dependencies and `keys.txt` are ready, the menu actions are ready to run.

### 2. ZNS LiteForge - 9 quest actions

Runs `app/zns_liteforge_7in1.py`.

Attempts the current ZNS LiteForge quest flow:

1. Say GM
2. Say GN
3. Mint Domain
4. Deploy NFT
5. Deploy Token
6. Deploy SC
7. Create NFT
8. Mint NFT
9. Vote

If a wallet has insufficient zkLTC for a step, that step is skipped and the script continues.

### 3. LiteForge bridge - zkLTC to Sepolia

Runs `app/liteforge_bridge.py`.

Initiates a native bridge withdrawal from LiteForge to Sepolia. Recipient is the same wallet. The menu asks for min/max amount and randomizes the amount per wallet.

### 4. LiteForge bridge claim - Sepolia

Runs `app/liteforge_claim.js`.

Claims completed LiteForge bridge withdrawals on Sepolia. Source withdrawal data is read from bridge logs and LiteForge explorer history.

The menu claims all ready withdrawals per wallet immediately.

### 5. WolfDex - swap/liquidity/farm/casino

Runs `app/wolfdex_actions.py`.

Can perform:

1. Swap zkLTC to selected token
2. Optional extra swap to LITVM
3. Add zkLTC/LITVM liquidity
4. Stake remaining LITVM
5. Casino coinflip

Prompts for token and amount settings.

### 6. OnChainGM LiteForge - GM + deploy

Runs `app/onchaingm_liteforge.py`.

Attempts:

1. GM on LitVM LiteForge
2. Deploy contract on LitVM LiteForge

GM cooldown is checked automatically. Deploy can still run if GM is on cooldown.

### 7. Infinityname LiteForge - mint .litevm

Runs `app/infinityname_liteforge.py`.

Mints one unique `.litevm` domain per wallet. The `.litevm` suffix is fixed, and the script creates randomized unique labels automatically.

### 8. MidasPredict - faucet/buy/sell/redeem

Opens the MidasPredict submenu. See the dedicated section below.

### 9. LiteForge - native zkLTC balance checker

Runs `app/liteforge_native_balance.js`.

Checks native zkLTC balance for all wallets in `keys.txt` and prints every balance plus total.

### 10. LitVMSwap - swaps

Runs `app/litvmswap_swaps.py`.

Sends real swaps through the LitVMSwap LiteForge router:

- source token: native `zkLTC`
- router: `0xF456737D17C2Bbb348fd4F7D1b000D62A46FB3b5`
- wrapped native: `0x315374AA9b5536037Cc1Efeea2439CCC0913A77e`

The menu asks for:

- target token: `ZKUSDC`, `LitVMSwap`, `ZKUSDT`, `LETH`, `ZKBTC`, `LXRP`, `brBNB`, or random
- min/max swaps per wallet
- min/max native `zkLTC` amount per swap

Slippage is fixed by the menu at 300 bps (3%). The script runs all wallets from `keys.txt` through `app/run_all_keys.py`.

## MidasPredict Submenu

Midas scripts use:

- API: `https://predict-testnet-api.midashand.xyz/api`
- default RPC: `https://liteforge.rpc.caldera.xyz/http`
- wallets from `keys.txt`

### 1. Faucet USDC / zkLTC

Runs `app/midaspredict_faucet.js`.

Requests Midas faucet for all wallets. Supports:

- USDC
- zkLTC
- both

The script does not use a local faucet cooldown. It sends the request and logs the site API response directly, including 429/400 errors.

### 2. Daily check-in

Runs `app/midaspredict_checkin.js`.

Does Midas daily check-in for all wallets. If a wallet is already checked in, the API response is logged and the script moves on.

### 3. Random buy events

Runs `app/midaspredict_trader.js random-buy` for all wallets.

Prompts for:

- source: standard, quick, or all
- min/max number of bets per wallet
- USDC total percent of starting balance, or min/max fixed trade amount
- market scan limit

The script picks a random bet count inside the entered min/max range for each wallet.

If USDC percent is entered, the script reads the wallet's starting USDC balance once, splits the total percent across the picked number of planned bets, and sizes each bet from that fixed starting balance. Example: picked count `3` and `90%` means each bet gets a 30% USDC spend budget before the wallet balance changes.

If USDC percent is left empty, min/max is target collateral spend.

Slippage is fixed by the menu at 300 bps (3%).

For native zkLTC/WZKLTC markets, the script ignores the entered collateral amount and sizes the trade as a random 10-30% of the wallet native balance, then applies market min/max checks.

Outcome is always random.

### 4. Reward tasks trades

Runs `app/midaspredict_trader.js tasks` for all wallets.

Before trading, the script authorizes each wallet and activates available reward quests through the same backend API used by the site:

- `GET /quests/status`
- `POST /quests/start`
- `POST /quests/claim`

Then it attempts visible reward tasks:

- first trade today
- trade in 2 different markets
- make 3 trades
- trade in a boosted market

Uses random outcomes and target collateral sizing.

You can enter a USDC total percent instead of fixed min/max. Reward tasks use 3 trades, so `90%` means about 30% of the starting USDC balance per trade.

After trades, it checks quest status again and claims claimable rewards.

Midas quest progress is indexed with a delay. The menu waits 8 minutes after the all-wallet trading pass, then runs a second all-wallet `claim-quests` pass to claim rewards that became claimable after indexing.

### 5. Sell all active positions

Runs `app/midaspredict_trader.js sell-all` for all wallets.

The script asks the Midas API for each wallet's active positions, checks the actual outcome-share balance on LitEVM, and sells the available shares.

Slippage is fixed by the menu at 300 bps (3%). Expired/resolved/zero-balance positions are skipped and logged.

### 6. Claim closed trades

Runs `app/midaspredict_trader.js redeem-all` for all wallets.

The script asks the Midas API for closed/resolved positions, deduplicates markets, then calls the market contract `redeem()` on LitEVM. Non-redeemable or already-claimed markets are skipped or logged as failed without stopping the full wallet pass.

### 7. Manual redeem

Runs `app/midaspredict_trader.js redeem`.

Single-wallet redeem for a resolved/closed market. The market must be in a redeemable state.

## Direct Commands

Examples for manual CLI runs:

```powershell
node app\liteforge_native_balance.js --all
node app\midaspredict_faucet.js --token usdc --all --send
node app\midaspredict_checkin.js --all --send
node app\midaspredict_trader.js random-buy --source all --count 2 --amount-min 10 --amount-max 100 --auto-min-trade --send
node app\midaspredict_trader.js random-buy --source standard --count-min 2 --count-max 4 --usdc-percent 90 --auto-min-trade --send
node app\midaspredict_trader.js sell-all --slippage-bps 300 --send
node app\midaspredict_trader.js redeem-all --send
python app\litvmswap_swaps.py --swap-token random --swaps 1-3 --amount 0.001-0.003 --slippage-bps 300 --send
```

## Logs

Each run writes a timestamped log to `logs/`.

If an action fails, check the latest log first. The menu prints the last matching log path after most runs.

## Public Release Checklist

Before publishing:

- `keys.txt` is absent
- `proxies.txt` is absent
- `wallet_addresses.txt` is absent or contains no private list
- `faucet_addresses.txt` is absent or contains no private list
- `logs/` is absent
- `state/` is absent
- `tmp/` is absent
- `node_modules/` is absent
- `.env` is absent
