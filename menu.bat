@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
title LitVMassasas menu
cd /d "%~dp0"

if not exist logs mkdir logs

:menu
cls
echo ============================================
echo  LitVMassasas - main menu
echo ============================================
echo.
echo  1. Install dependencies
echo  2. ZNS LiteForge - 9 quest actions
echo  3. LiteForge bridge - zkLTC to Sepolia
echo  4. LiteForge bridge claim - Sepolia
echo  5. WolfDex - swap/liquidity/farm/casino
echo  6. OnChainGM LiteForge - GM + deploy
echo  7. Infinityname LiteForge - mint .litevm
echo  8. MidasPredict - faucet/buy/sell/redeem
echo  9. LiteForge - native zkLTC balance checker
echo  10. LitVMSwap - swaps
echo  0. Exit
echo.
set /p CHOICE=Choose action: 

if "%CHOICE%"=="1" goto install_deps
if "%CHOICE%"=="2" goto zns_liteforge_7in1
if "%CHOICE%"=="3" goto liteforge_bridge
if "%CHOICE%"=="4" goto liteforge_claim
if "%CHOICE%"=="5" goto wolfdex
if "%CHOICE%"=="6" goto onchaingm_liteforge
if "%CHOICE%"=="7" goto iname
if "%CHOICE%"=="8" goto midaspredict
if "%CHOICE%"=="9" goto liteforge_native_balance
if "%CHOICE%"=="10" goto litvmswap
if "%CHOICE%"=="0" exit /b 0

echo.
echo [ERROR] Unknown menu option.
pause
goto menu

:check_python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo Install Python and run option 1.
    pause
    goto menu
)
exit /b 0

:check_node
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found in PATH.
    echo Install Node.js and run option 1.
    pause
    goto menu
)
exit /b 0

:zns_vote
cls
call :check_python
echo ============================================
echo  ZNS LiteForge - VOTE
echo ============================================
echo.
echo This sends real ZNS vote transactions on LiteForge.
echo Current on-chain vote fee is checked automatically.
echo Script uses zero referral by default.
echo Vote count is limited by script to 1..20.
echo You can enter a fixed value or range, for example 1-3.
echo.
set /p ZNS_VOTE_COUNT=Vote count [1]: 
if "%ZNS_VOTE_COUNT%"=="" set ZNS_VOTE_COUNT=1
echo.
python app\run_all_keys.py --pause-min 5 --pause-max 15 -- python app\zns_liteforge_vote.py --count "%ZNS_VOTE_COUNT%" --send
set EXIT_CODE=%ERRORLEVEL%
echo.
for /f "delims=" %%F in ('dir /b /a:-d /o:-d "logs\zns_liteforge_vote_*.log" 2^>nul') do (
    set LAST_ZNS_VOTE_LOG=logs\%%F
    goto zns_vote_log_found
)
set LAST_ZNS_VOTE_LOG=
:zns_vote_log_found
if "%EXIT_CODE%"=="0" (
    echo [OK] ZNS vote transaction completed.
) else (
    echo [ERROR] ZNS vote transaction failed.
)
if not "%LAST_ZNS_VOTE_LOG%"=="" (
    echo Last ZNS vote log: %CD%\%LAST_ZNS_VOTE_LOG%
) else (
    echo [WARN] ZNS vote log was not found.
)
pause
goto menu

:zns_liteforge_7in1
cls
call :check_python
echo ============================================
echo  ZNS LiteForge - QUEST ACTIONS
echo ============================================
echo.
echo This sends real LiteForge transactions.
echo First joins Streak Wars / litvm quest.
echo Then runs current ZNS 9-action quest flow:
echo   1. Say GM
echo   2. Say GN
echo   3. Mint Domain
echo   4. Deploy NFT
echo   5. Deploy Token
echo   6. Deploy SC
echo   7. Create NFT
echo   8. Mint NFT
echo   9. Vote
echo.
echo Referral is fixed to zero address.
echo If balance is not enough, that step is skipped and the script continues.
echo.
set ZNS_RUN_STATUS=logs\zns_liteforge_run_status.txt
if exist "%ZNS_RUN_STATUS%" del "%ZNS_RUN_STATUS%"
python app\run_all_keys.py --pause-min 5 --pause-max 15 --success-if-any --status-file "%ZNS_RUN_STATUS%" -- python app\zns_liteforge_7in1.py --send
set EXIT_CODE=%ERRORLEVEL%
echo.
set LAST_ZNS_7IN1_LOG=
for %%F in (logs\zns_liteforge_7in1_*.log) do set LAST_ZNS_7IN1_LOG=%%F
if exist "%ZNS_RUN_STATUS%" (
    for /f "tokens=1,2 delims==" %%A in (%ZNS_RUN_STATUS%) do (
        if "%%A"=="success_count" if not "%%B"=="0" set EXIT_CODE=0
    )
)
if "%EXIT_CODE%"=="0" (
    echo [OK] ZNS 9 actions completed.
) else (
    echo [ERROR] ZNS 9 actions failed.
)
if not "%LAST_ZNS_7IN1_LOG%"=="" (
    echo Last ZNS 9-action log: %CD%\%LAST_ZNS_7IN1_LOG%
) else (
    echo [WARN] ZNS 9-action log was not found.
)
pause
goto menu

:liteforge_bridge
cls
call :check_python
echo ============================================
echo  LiteForge bridge - zkLTC to Sepolia
echo ============================================
echo.
echo This sends a real LiteForge transaction.
echo Amount is limited by script to 0.001..0.04 zkLTC.
echo Recipient: your own wallet from keys.txt.
echo Amount is randomized per wallet from min/max.
echo.
set /p BRIDGE_AMOUNT_MIN=Min amount zkLTC [0.001]: 
if "%BRIDGE_AMOUNT_MIN%"=="" set BRIDGE_AMOUNT_MIN=0.001
set /p BRIDGE_AMOUNT_MAX=Max amount zkLTC [0.004]: 
if "%BRIDGE_AMOUNT_MAX%"=="" set BRIDGE_AMOUNT_MAX=0.004
set "BRIDGE_AMOUNT=%BRIDGE_AMOUNT_MIN%-%BRIDGE_AMOUNT_MAX%"
echo.
python app\run_all_keys.py --pause-min 5 --pause-max 15 -- python app\liteforge_bridge.py --amount "%BRIDGE_AMOUNT%" --send
set EXIT_CODE=%ERRORLEVEL%
echo.
for /f "delims=" %%F in ('dir /b /a:-d /o:-d "logs\liteforge_bridge_*.log" 2^>nul') do (
    set LAST_BRIDGE_LOG=logs\%%F
    goto bridge_log_found
)
set LAST_BRIDGE_LOG=
:bridge_log_found
if "%EXIT_CODE%"=="0" (
    echo [OK] Bridge withdrawal initiated.
) else (
    echo [ERROR] Bridge failed.
)
if not "%LAST_BRIDGE_LOG%"=="" (
    echo Last bridge log: %CD%\%LAST_BRIDGE_LOG%
) else (
    echo [WARN] Bridge log was not found.
)
pause
goto menu

:liteforge_claim
cls
call :check_python
call :check_node
echo ============================================
echo  LiteForge bridge claim - Sepolia
echo ============================================
echo.
echo This claims completed LiteForge native bridge withdrawals on Sepolia.
echo Source withdrawals are taken from logs and LiteForge explorer history.
echo All confirmed and unclaimed outbox messages are executed.
echo.
python app\run_all_keys.py --pause-min 5 --pause-max 15 --success-if-any -- node app\liteforge_claim.js --send --all
set EXIT_CODE=%ERRORLEVEL%
echo.
set LAST_CLAIM_LOG=
for %%F in (logs\liteforge_claim_*.log) do set LAST_CLAIM_LOG=%%F
if "%EXIT_CODE%"=="0" (
    echo [OK] LiteForge claim completed.
) else (
    echo [ERROR] LiteForge claim failed or no ready claims were found.
)
if not "%LAST_CLAIM_LOG%"=="" (
    echo Last LiteForge claim log: %CD%\%LAST_CLAIM_LOG%
) else (
    echo [WARN] LiteForge claim log was not found.
)
pause
goto menu

:wolfdex
cls
call :check_python
echo ============================================
echo  WolfDex - SWAP / LIQUIDITY / FARM / CASINO
echo ============================================
echo.
echo This sends real LiteForge transactions on WolfDex.
echo Actions:
echo   1. Swap zkLTC to selected token
echo   2. If selected token is not LITVM, optionally swap zkLTC to LITVM too
echo   3. Add zkLTC/LITVM liquidity
echo   4. Stake remaining LITVM
echo   5. Casino coinflip
echo.
echo Swap amounts are selected here.
echo You can enter fixed values or ranges, for example 0.001 or 0.001-0.003.
echo Script limits swap/liquidity amounts to 0.05 zkLTC max.
echo Casino min is checked on-chain; current frontend min is about 0.01 zkLTC.
echo.
echo Swap token:
echo   1. LITVM
echo   2. WDEX
echo   3. BNB
echo   4. MON
echo   5. HYPE
echo   6. ETH
echo   7. Random
set WOLF_TOKEN=
set /p WOLF_TOKEN_CHOICE=Choose token [1]: 
if "%WOLF_TOKEN_CHOICE%"=="" set WOLF_TOKEN_CHOICE=1
if "%WOLF_TOKEN_CHOICE%"=="1" set WOLF_TOKEN=LITVM
if "%WOLF_TOKEN_CHOICE%"=="2" set WOLF_TOKEN=WDEX
if "%WOLF_TOKEN_CHOICE%"=="3" set WOLF_TOKEN=BNB
if "%WOLF_TOKEN_CHOICE%"=="4" set WOLF_TOKEN=MON
if "%WOLF_TOKEN_CHOICE%"=="5" set WOLF_TOKEN=HYPE
if "%WOLF_TOKEN_CHOICE%"=="6" set WOLF_TOKEN=ETH
if "%WOLF_TOKEN_CHOICE%"=="7" set WOLF_TOKEN=random
if "%WOLF_TOKEN%"=="" (
    echo [ERROR] Unknown token option.
    pause
    goto menu
)
set /p WOLF_SWAP_AMOUNT=Main swap amount zkLTC, fixed/range [0.001]: 
if "%WOLF_SWAP_AMOUNT%"=="" set WOLF_SWAP_AMOUNT=0.001
set /p WOLF_LITVM_AMOUNT=Extra LITVM swap amount zkLTC, fixed/range, 0 to skip [0.001]: 
if "%WOLF_LITVM_AMOUNT%"=="" set WOLF_LITVM_AMOUNT=0.001
set /p WOLF_LP_AMOUNT=Liquidity zkLTC amount, 0 to skip [0.001]: 
if "%WOLF_LP_AMOUNT%"=="" set WOLF_LP_AMOUNT=0.001
set /p WOLF_STAKE_PCT=Stake percent of remaining LITVM, 0 to skip [50]: 
if "%WOLF_STAKE_PCT%"=="" set WOLF_STAKE_PCT=50
set /p WOLF_CASINO_BET=Casino coinflip bet zkLTC, 0 to skip [0.01]: 
if "%WOLF_CASINO_BET%"=="" set WOLF_CASINO_BET=0.01
echo.
python app\run_all_keys.py --pause-min 5 --pause-max 15 -- python app\wolfdex_actions.py --swap-token "%WOLF_TOKEN%" --swap-amount "%WOLF_SWAP_AMOUNT%" --litvm-swap-amount "%WOLF_LITVM_AMOUNT%" --liquidity-amount "%WOLF_LP_AMOUNT%" --stake-pct "%WOLF_STAKE_PCT%" --casino-bet "%WOLF_CASINO_BET%" --send
set EXIT_CODE=%ERRORLEVEL%
echo.
set LAST_WOLFDEX_LOG=
for %%F in (logs\wolfdex_actions_*.log) do set LAST_WOLFDEX_LOG=%%F
if "%EXIT_CODE%"=="0" (
    echo [OK] WolfDex actions completed.
) else (
    echo [ERROR] WolfDex actions failed.
)
if not "%LAST_WOLFDEX_LOG%"=="" (
    echo Last WolfDex log: %CD%\%LAST_WOLFDEX_LOG%
) else (
    echo [WARN] WolfDex log was not found.
)
pause
goto menu

:onchaingm_liteforge
cls
call :check_python
echo ============================================
echo  OnChainGM LiteForge - GM + DEPLOY
echo ============================================
echo.
echo This sends real LiteForge transactions through OnChainGM contracts.
echo Actions:
echo   1. GM on LitVM LiteForge
echo   2. Deploy contract on LitVM LiteForge
echo.
echo GM cooldown is checked automatically.
echo If GM is on cooldown, deploy still runs.
echo Each action costs the current on-chain/frontend fee.
echo.
python app\run_all_keys.py --pause-min 5 --pause-max 15 --success-if-any -- python app\onchaingm_liteforge.py --send
set EXIT_CODE=%ERRORLEVEL%
echo.
set LAST_ONCHAINGM_LOG=
for %%F in (logs\onchaingm_liteforge_*.log) do set LAST_ONCHAINGM_LOG=%%F
if "%EXIT_CODE%"=="0" (
    echo [OK] OnChainGM actions completed.
) else (
    echo [ERROR] OnChainGM actions failed.
)
if not "%LAST_ONCHAINGM_LOG%"=="" (
    echo Last OnChainGM log: %CD%\%LAST_ONCHAINGM_LOG%
) else (
    echo [WARN] OnChainGM log was not found.
)
pause
goto menu

:iname
cls
call :check_python
echo ============================================
echo  Infinityname LiteForge - MINT .LITEVM
echo ============================================
echo.
echo This sends real LiteForge transactions on Infinityname.
echo Contract: 0x76a816EFa69e3183972ff7a231F5C8d7b065d9De
echo Referral is fixed from your Infinityname URL.
echo One wallet = one unique domain.
echo.
echo Domain suffix is fixed on-chain: .litevm
echo Script auto-builds random unique labels per wallet, for example:
echo   kazenor7.litevm
echo   farmvexluro2.litevm
echo Sequential names are not used as the main pattern.
echo.
python app\run_all_keys.py --pause-min 5 --pause-max 15 --success-if-any -- python app\infinityname_liteforge.py --base "litevm" --send
set EXIT_CODE=%ERRORLEVEL%
echo.
set LAST_INFINITYNAME_LOG=
for %%F in (logs\infinityname_liteforge_*.log) do set LAST_INFINITYNAME_LOG=%%F
if "%EXIT_CODE%"=="0" (
    echo [OK] Infinityname mint completed.
) else (
    echo [ERROR] Infinityname mint failed.
)
if not "%LAST_INFINITYNAME_LOG%"=="" (
    echo Last Infinityname log: %CD%\%LAST_INFINITYNAME_LOG%
) else (
    echo [WARN] Infinityname log was not found.
)
pause
goto menu

:midaspredict
cls
call :check_node
echo ============================================
echo  MidasPredict - FAUCET / CHECK-IN / BUY / SELL / REDEEM
echo ============================================
echo.
echo Trading uses LitEVM/LiteForge RPC by default:
echo   https://liteforge.rpc.caldera.xyz/http
echo You can override it with MIDAS_RPC_URL or EVM_RPC_URL.
echo Real transactions also need:
echo   BOT_PRIVATE_KEY or keys.txt + KEY_INDEX
echo.
echo Faucet/check-in/random/tasks/sell-all/claim-trades run all wallets immediately.
echo Manual redeem still uses one wallet from KEY_INDEX.
echo.
echo Actions:
echo   1. Faucet USDC / zkLTC
echo   2. Daily check-in
echo   3. Random buy events
echo   4. Reward tasks trades
echo   5. Sell all active positions
echo   6. Claim closed trades
echo   7. Manual redeem
set MIDAS_ACTION=
set /p MIDAS_CHOICE=Choose action [1]: 
if "%MIDAS_CHOICE%"=="" set MIDAS_CHOICE=1
if "%MIDAS_CHOICE%"=="1" set MIDAS_ACTION=faucet
if "%MIDAS_CHOICE%"=="2" set MIDAS_ACTION=checkin
if "%MIDAS_CHOICE%"=="3" set MIDAS_ACTION=random-buy
if "%MIDAS_CHOICE%"=="4" set MIDAS_ACTION=tasks
if "%MIDAS_CHOICE%"=="5" set MIDAS_ACTION=sell-all
if "%MIDAS_CHOICE%"=="6" set MIDAS_ACTION=redeem-all
if "%MIDAS_CHOICE%"=="7" set MIDAS_ACTION=redeem
if "%MIDAS_ACTION%"=="" (
    echo [ERROR] Unknown action.
    pause
    goto menu
)
set MIDAS_ARGS=
set MIDAS_RUN_ALL=0
if "%MIDAS_ACTION%"=="faucet" (
    echo.
    echo Token:
    echo   1. USDC
    echo   2. zkLTC
    echo   3. Both
    set MIDAS_FAUCET_TOKEN=usdc
    set /p MIDAS_FAUCET_TOKEN_CHOICE=Choose token [1]: 
    if "!MIDAS_FAUCET_TOKEN_CHOICE!"=="" set MIDAS_FAUCET_TOKEN_CHOICE=1
    if "!MIDAS_FAUCET_TOKEN_CHOICE!"=="1" set MIDAS_FAUCET_TOKEN=usdc
    if "!MIDAS_FAUCET_TOKEN_CHOICE!"=="2" set MIDAS_FAUCET_TOKEN=zkltc
    if "!MIDAS_FAUCET_TOKEN_CHOICE!"=="3" set MIDAS_FAUCET_TOKEN=both
    set MIDAS_FAUCET_ARGS=--token "!MIDAS_FAUCET_TOKEN!" --all --pause-min 4 --pause-max 10 --send
    echo Running all wallets from keys.txt...
    echo.
    node app\midaspredict_faucet.js !MIDAS_FAUCET_ARGS!
    set EXIT_CODE=%ERRORLEVEL%
    goto midas_done
)
if "%MIDAS_ACTION%"=="checkin" (
    echo.
    echo Running daily check-in for all wallets from keys.txt...
    echo.
    node app\midaspredict_checkin.js --all --pause-min 4 --pause-max 10 --send
    set EXIT_CODE=%ERRORLEVEL%
    goto midas_done
)
if "%MIDAS_ACTION%"=="random-buy" (
    echo Source:
    echo   1. Standard open markets
    echo   2. Quick live markets
    echo   3. All
    set MIDAS_SOURCE=standard
    set /p MIDAS_SOURCE_CHOICE=Choose source [1]: 
    if "!MIDAS_SOURCE_CHOICE!"=="" set MIDAS_SOURCE_CHOICE=1
    if "!MIDAS_SOURCE_CHOICE!"=="1" set MIDAS_SOURCE=standard
    if "!MIDAS_SOURCE_CHOICE!"=="2" set MIDAS_SOURCE=quick
    if "!MIDAS_SOURCE_CHOICE!"=="3" set MIDAS_SOURCE=all
    set /p MIDAS_COUNT_MIN=Min bets count [1]: 
    if "!MIDAS_COUNT_MIN!"=="" set MIDAS_COUNT_MIN=1
    set /p MIDAS_COUNT_MAX=Max bets count [!MIDAS_COUNT_MIN!]: 
    if "!MIDAS_COUNT_MAX!"=="" set MIDAS_COUNT_MAX=!MIDAS_COUNT_MIN!
    set /p MIDAS_USDC_PERCENT=USDC total percent of starting balance, e.g. 90 [fixed amount]: 
    set /p MIDAS_LIMIT=Markets scan limit [20]: 
    if "!MIDAS_LIMIT!"=="" set MIDAS_LIMIT=20
    set MIDAS_SLIPPAGE=300
    if "!MIDAS_USDC_PERCENT!"=="" (
        set /p MIDAS_AMOUNT_MIN=Min trade amount in collateral: 
        set /p MIDAS_AMOUNT_MAX=Max trade amount in collateral: 
        set MIDAS_ARGS=--source "!MIDAS_SOURCE!" --count-min "!MIDAS_COUNT_MIN!" --count-max "!MIDAS_COUNT_MAX!" --amount-min "!MIDAS_AMOUNT_MIN!" --amount-max "!MIDAS_AMOUNT_MAX!" --limit "!MIDAS_LIMIT!" --slippage-bps "!MIDAS_SLIPPAGE!" --auto-min-trade --send
    ) else (
        set MIDAS_ARGS=--source "!MIDAS_SOURCE!" --count-min "!MIDAS_COUNT_MIN!" --count-max "!MIDAS_COUNT_MAX!" --usdc-percent "!MIDAS_USDC_PERCENT!" --limit "!MIDAS_LIMIT!" --slippage-bps "!MIDAS_SLIPPAGE!" --auto-min-trade --send
    )
    set MIDAS_RUN_ALL=1
)
if "%MIDAS_ACTION%"=="tasks" (
    echo This tries to complete visible Rewards tasks:
    echo   - first trade today
    echo   - trade in 2 different markets
    echo   - make 3 trades
    echo   - trade in a boosted market
    echo.
    set /p MIDAS_USDC_PERCENT=USDC total percent of starting balance for 3 trades, e.g. 90 [fixed amount]: 
    set /p MIDAS_LIMIT=Markets scan limit [100]: 
    if "!MIDAS_LIMIT!"=="" set MIDAS_LIMIT=100
    set MIDAS_SLIPPAGE=300
    if "!MIDAS_USDC_PERCENT!"=="" (
        set /p MIDAS_AMOUNT_MIN=Min trade amount in collateral: 
        set /p MIDAS_AMOUNT_MAX=Max trade amount in collateral: 
        set MIDAS_ARGS=--amount-min "!MIDAS_AMOUNT_MIN!" --amount-max "!MIDAS_AMOUNT_MAX!" --limit "!MIDAS_LIMIT!" --slippage-bps "!MIDAS_SLIPPAGE!" --auto-min-trade --send
    ) else (
        set MIDAS_ARGS=--usdc-percent "!MIDAS_USDC_PERCENT!" --limit "!MIDAS_LIMIT!" --slippage-bps "!MIDAS_SLIPPAGE!" --auto-min-trade --send
    )
    set MIDAS_RUN_ALL=1
)
if "%MIDAS_ACTION%"=="sell-all" (
    echo.
    echo Selling all active Midas positions for all wallets from keys.txt...
    echo.
    set MIDAS_SLIPPAGE=300
    set MIDAS_ARGS=--slippage-bps "!MIDAS_SLIPPAGE!" --send
    set MIDAS_RUN_ALL=1
)
if "%MIDAS_ACTION%"=="redeem-all" (
    echo.
    echo Claiming closed Midas trades for all wallets from keys.txt...
    echo.
    set MIDAS_ARGS=--send
    set MIDAS_RUN_ALL=1
)
if "%MIDAS_ACTION%"=="redeem" (
    set /p MIDAS_MARKET=Market address: 
    set MIDAS_ARGS=--market "%MIDAS_MARKET%" --send
)
echo.
if "%MIDAS_RUN_ALL%"=="1" (
    python app\run_all_keys.py --pause-min 5 --pause-max 15 --success-if-any -- node app\midaspredict_trader.js %MIDAS_ACTION% %MIDAS_ARGS%
) else (
    node app\midaspredict_trader.js %MIDAS_ACTION% %MIDAS_ARGS%
)
set EXIT_CODE=%ERRORLEVEL%
if "%MIDAS_ACTION%"=="tasks" (
    echo.
    echo Waiting 8 minutes for Midas quest indexer...
    timeout /t 480 /nobreak
    echo.
    echo Claiming completed Midas reward quests for all wallets...
    python app\run_all_keys.py --pause-min 2 --pause-max 5 --success-if-any -- node app\midaspredict_trader.js claim-quests
    if errorlevel 1 set EXIT_CODE=1
)
:midas_done
echo.
set LAST_MIDAS_LOG=
for /f "delims=" %%F in ('dir /b /a:-d /o:-d "logs\midaspredict*.log" 2^>nul') do (
    set LAST_MIDAS_LOG=%CD%\logs\%%F
    goto midas_log_found
)
:midas_log_found
if "%EXIT_CODE%"=="0" (
    echo [OK] MidasPredict action completed.
) else (
    echo [ERROR] MidasPredict action failed.
)
if not "%LAST_MIDAS_LOG%"=="" (
    echo Last MidasPredict log: %LAST_MIDAS_LOG%
) else (
    echo [WARN] MidasPredict log was not found.
)
pause
goto menu

:liteforge_native_balance
cls
call :check_node
echo ============================================
echo  LiteForge - native zkLTC balance checker
echo ============================================
echo.
echo RPC:
echo   https://liteforge.rpc.caldera.xyz/http
echo You can override it with LITEFORGE_RPC_URL, MIDAS_RPC_URL, or EVM_RPC_URL.
echo.
echo Checking all wallets from keys.txt...
echo.
node app\liteforge_native_balance.js --all
set EXIT_CODE=%ERRORLEVEL%
echo.
set LAST_LITE_BALANCE_LOG=
for %%F in (logs\liteforge_native_balance_*.log) do set LAST_LITE_BALANCE_LOG=%%F
if "%EXIT_CODE%"=="0" (
    echo [OK] LiteForge balance check completed.
) else (
    echo [ERROR] LiteForge balance check failed.
)
if not "%LAST_LITE_BALANCE_LOG%"=="" (
    echo Last balance log: %CD%\%LAST_LITE_BALANCE_LOG%
) else (
    echo [WARN] Balance log was not found.
)
pause
goto menu

:litvmswap
cls
call :check_python
echo ============================================
echo  LitVMSwap - SWAPS
echo ============================================
echo.
echo This sends real LiteForge transactions through LitVMSwap.
echo Source token is native zkLTC.
echo Router:
echo   0xF456737D17C2Bbb348fd4F7D1b000D62A46FB3b5
echo.
echo Target token:
echo   1. ZKUSDC
echo   2. LitVMSwap
echo   3. ZKUSDT
echo   4. LETH
echo   5. ZKBTC
echo   6. LXRP
echo   7. brBNB
echo   8. Random
set LITVMSWAP_TOKEN=
set /p LITVMSWAP_TOKEN_CHOICE=Choose token [8]: 
if "%LITVMSWAP_TOKEN_CHOICE%"=="" set LITVMSWAP_TOKEN_CHOICE=8
if "%LITVMSWAP_TOKEN_CHOICE%"=="1" set LITVMSWAP_TOKEN=ZKUSDC
if "%LITVMSWAP_TOKEN_CHOICE%"=="2" set LITVMSWAP_TOKEN=LITVMSWAP
if "%LITVMSWAP_TOKEN_CHOICE%"=="3" set LITVMSWAP_TOKEN=ZKUSDT
if "%LITVMSWAP_TOKEN_CHOICE%"=="4" set LITVMSWAP_TOKEN=LETH
if "%LITVMSWAP_TOKEN_CHOICE%"=="5" set LITVMSWAP_TOKEN=ZKBTC
if "%LITVMSWAP_TOKEN_CHOICE%"=="6" set LITVMSWAP_TOKEN=LXRP
if "%LITVMSWAP_TOKEN_CHOICE%"=="7" set LITVMSWAP_TOKEN=BRBNB
if "%LITVMSWAP_TOKEN_CHOICE%"=="8" set LITVMSWAP_TOKEN=random
if "%LITVMSWAP_TOKEN%"=="" (
    echo [ERROR] Unknown token option.
    pause
    goto menu
)
set /p LITVMSWAP_COUNT_MIN=Min swaps per wallet [1]: 
if "%LITVMSWAP_COUNT_MIN%"=="" set LITVMSWAP_COUNT_MIN=1
set /p LITVMSWAP_COUNT_MAX=Max swaps per wallet [%LITVMSWAP_COUNT_MIN%]: 
if "%LITVMSWAP_COUNT_MAX%"=="" set LITVMSWAP_COUNT_MAX=%LITVMSWAP_COUNT_MIN%
set /p LITVMSWAP_AMOUNT_MIN=Min amount per swap zkLTC [0.001]: 
if "%LITVMSWAP_AMOUNT_MIN%"=="" set LITVMSWAP_AMOUNT_MIN=0.001
set /p LITVMSWAP_AMOUNT_MAX=Max amount per swap zkLTC [%LITVMSWAP_AMOUNT_MIN%]: 
if "%LITVMSWAP_AMOUNT_MAX%"=="" set LITVMSWAP_AMOUNT_MAX=%LITVMSWAP_AMOUNT_MIN%
set LITVMSWAP_SLIPPAGE=300
set "LITVMSWAP_SWAPS=%LITVMSWAP_COUNT_MIN%-%LITVMSWAP_COUNT_MAX%"
set "LITVMSWAP_AMOUNT=%LITVMSWAP_AMOUNT_MIN%-%LITVMSWAP_AMOUNT_MAX%"
echo.
python app\run_all_keys.py --pause-min 5 --pause-max 15 --success-if-any -- python app\litvmswap_swaps.py --swap-token "%LITVMSWAP_TOKEN%" --swaps "%LITVMSWAP_SWAPS%" --amount "%LITVMSWAP_AMOUNT%" --slippage-bps "%LITVMSWAP_SLIPPAGE%" --send
set EXIT_CODE=%ERRORLEVEL%
echo.
set LAST_LITVMSWAP_LOG=
for /f "delims=" %%F in ('dir /b /a:-d /o:-d "logs\litvmswap_swaps_*.log" 2^>nul') do (
    set LAST_LITVMSWAP_LOG=%CD%\logs\%%F
    goto litvmswap_log_found
)
:litvmswap_log_found
if "%EXIT_CODE%"=="0" (
    echo [OK] LitVMSwap swaps completed.
) else (
    echo [ERROR] LitVMSwap swaps failed.
)
if not "%LAST_LITVMSWAP_LOG%"=="" (
    echo Last LitVMSwap log: %LAST_LITVMSWAP_LOG%
) else (
    echo [WARN] LitVMSwap log was not found.
)
pause
goto menu

:install_deps
cls
echo ============================================
echo  Installing dependencies
echo ============================================
echo.
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    pause
    goto menu
)
python --version
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
where npm >nul 2>&1
if not errorlevel 1 (
    if exist package.json npm install
) else (
    echo [WARN] npm not found; LiteForge claim JS dependencies were not checked.
)
if not exist logs mkdir logs
echo.
echo [OK] Dependencies step finished.
pause
goto menu
