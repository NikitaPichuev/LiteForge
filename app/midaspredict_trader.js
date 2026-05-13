const fs = require("fs");
const https = require("https");
const path = require("path");

const { ethers } = require("ethers");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const KEYS_FILE = path.join(PROJECT_ROOT, "keys.txt");
const LOGS_DIR = path.join(PROJECT_ROOT, "logs");
fs.mkdirSync(LOGS_DIR, { recursive: true });

const LOG_FILE = path.join(
  LOGS_DIR,
  `midaspredict_${new Date().toISOString().replace(/[-:]/g, "").slice(0, 15).replace("T", "_")}.log`
);

const API_BASE = process.env.MIDAS_API_BASE || "https://predict-testnet-api.midashand.xyz/api";
const DEFAULT_RPC_URL = "https://liteforge.rpc.caldera.xyz/http";
const BPS = ethers.BigNumber.from(10_000);
const ADDRESS_RE = /^0x[0-9a-fA-F]{40}$/;
const MIDAS_MARKET_HELPER = "0xA10BaC04371b5DC33a3C2C938808335bb8c2d02e";

const ERC20_ABI = [
  "function approve(address spender, uint256 amount) returns (bool)",
  "function allowance(address owner, address spender) view returns (uint256)",
  "function decimals() view returns (uint8)",
  "function balanceOf(address account) view returns (uint256)",
  "function symbol() view returns (string)",
];

const ERC1155_ABI = [
  "function balanceOf(address account, uint256 id) view returns (uint256)",
  "function getTokenId(address market, uint256 outcomeIndex) view returns (uint256)",
];

const MIDAS_MARKET_ABI = [
  "function buy(uint8[] outcomes, uint256[] amounts, uint256 maxCost) payable",
  "function sell(uint8[] outcomes, uint256[] amounts, uint256 minReturn)",
  "function redeem()",
  "function getOutcomePurchaseCost(uint8[] outcomes, uint256[] amounts) view returns (uint256)",
  "function getOutcomeSaleReturn(uint8[] outcomes, uint256[] amounts) view returns (uint256)",
  "function getPrices() view returns (uint256[])",
  "function getStatus() view returns (uint8)",
  "function getCollateralToken() view returns (address)",
  "function getOutcomeCount() view returns (uint8)",
  "function getRedeemableAmountPerShare() view returns (uint256)",
  "function MARKET_OUTCOME() view returns (address)",
  "function getMarket() view returns (tuple(address resolver,uint40 expiresAt,uint40 startsAt,uint16 creatorFeeBps,address creator,uint40 resolvedAt,uint16 protocolFeeBpsOverride,uint8 outcomeCount,uint8 winningOutcome,uint8 status,bool overrideProtocolFeeBps,address collateralToken,address resolvedBy,uint256 initialSharesPerOutcome,uint256 collateralAmount,uint256 redeemableAmountPerShare,uint256 resolverFee,tuple(uint256 T0,uint256 alpha0Bps,uint256 T1,uint256 alpha1Bps,uint256 T2,uint256 alpha2Bps,uint256 c1_fp,uint256 c2_fp) alphaConfig))",
];

const MIDAS_MARKET_HELPER_ABI = [
  "function getSharesForCollateralInMarket(address market, uint8 outcome, uint256 collateralAmount) view returns (uint256)",
];

function timestamp() {
  return new Date().toTimeString().slice(0, 8);
}

function log(level, message) {
  const line = `${timestamp()}  ${level.padEnd(7)}  ${message}`;
  console.log(line);
  fs.appendFileSync(LOG_FILE, `${line}\n`, "utf8");
}

function usage() {
  console.log(`
MidasPredict trader

Required for trading:
  EVM_RPC_URL or MIDAS_RPC_URL (default: LiteForge RPC)
  BOT_PRIVATE_KEY or keys.txt + KEY_INDEX

Commands:
  node app\\midaspredict_trader.js system
  node app\\midaspredict_trader.js list-standard [--collateral 0x...]
  node app\\midaspredict_trader.js list-quick [--asset BTC,LTC] [--cycle 15]
  node app\\midaspredict_trader.js show --market 0x...
  node app\\midaspredict_trader.js buy --market 0x... --outcome 0 --amount 1 [--slippage-bps 100] [--send]
  node app\\midaspredict_trader.js random-buy --amount-min 1 --amount-max 3 [--count 1] [--count-min 1 --count-max 3] [--source standard|quick|all] [--auto-min-trade] [--send]
  node app\\midaspredict_trader.js random-buy --usdc-percent 90 --count 3 [--source standard|quick|all] [--auto-min-trade] [--send]
  node app\\midaspredict_trader.js tasks --amount-min 1 --amount-max 3 [--auto-min-trade] [--send]
  node app\\midaspredict_trader.js tasks --usdc-percent 90 [--auto-min-trade] [--send]
  node app\\midaspredict_trader.js sell --market 0x... --outcome 0 --amount 1 [--slippage-bps 100] [--send]
  node app\\midaspredict_trader.js sell-all [--slippage-bps 300] [--send]
  node app\\midaspredict_trader.js redeem --market 0x... [--send]
  node app\\midaspredict_trader.js redeem-all [--send]

system/list/show work through the public API and do not need RPC.
buy/sell/redeem use LitEVM/LiteForge RPC. Without --send the script only quotes/checks.
Single buy/sell --amount is in whole shares. sell-all sells active API positions for the selected wallet.
redeem-all claims closed claimable markets for the selected wallet.
Random/tasks --amount-min/max is target collateral spend.
--usdc-percent uses the wallet's starting USDC balance and splits the total percent across planned bets.
`);
}

function parseArgs() {
  const args = process.argv.slice(2);
  const command = args.shift();
  const parsed = {
    command,
    send: false,
    slippageBps: 100,
    limit: 20,
    count: 1,
    source: "standard",
    randomOutcome: true,
    uniqueMarkets: false,
    boostedOnly: false,
    autoMinTrade: false,
  };

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === "--send") {
      parsed.send = true;
    } else if (arg === "--market") {
      parsed.market = args[++i];
    } else if (arg === "--outcome") {
      parsed.outcome = Number.parseInt(args[++i], 10);
    } else if (arg === "--amount") {
      parsed.amount = args[++i];
    } else if (arg === "--amount-min") {
      parsed.amountMin = args[++i];
    } else if (arg === "--amount-max") {
      parsed.amountMax = args[++i];
    } else if (arg === "--usdc-percent") {
      parsed.usdcPercent = args[++i];
    } else if (arg === "--count") {
      parsed.count = Number.parseInt(args[++i], 10);
    } else if (arg === "--count-min") {
      parsed.countMin = Number.parseInt(args[++i], 10);
    } else if (arg === "--count-max") {
      parsed.countMax = Number.parseInt(args[++i], 10);
    } else if (arg === "--source") {
      parsed.source = String(args[++i] || "").toLowerCase();
    } else if (arg === "--unique-markets") {
      parsed.uniqueMarkets = true;
    } else if (arg === "--boosted-only") {
      parsed.boostedOnly = true;
    } else if (arg === "--auto-min-trade") {
      parsed.autoMinTrade = true;
    } else if (arg === "--slippage-bps") {
      parsed.slippageBps = Number.parseInt(args[++i], 10);
    } else if (arg === "--collateral") {
      const value = args[++i];
      if (!isAllValue(value)) parsed.collateral = value;
    } else if (arg === "--asset") {
      const value = args[++i];
      if (!isAllValue(value)) parsed.asset = value;
    } else if (arg === "--cycle") {
      const value = args[++i];
      if (!isAllValue(value)) parsed.cycle = Number.parseInt(value, 10);
    } else if (arg === "--limit") {
      parsed.limit = Number.parseInt(args[++i], 10);
    } else if (arg === "--rpc") {
      parsed.rpc = args[++i];
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return parsed;
}

function isAllValue(value) {
  return ["", "all", "*"].includes(String(value || "").trim().toLowerCase());
}

function readKeys() {
  if (!fs.existsSync(KEYS_FILE)) return [];
  return fs
    .readFileSync(KEYS_FILE, "utf8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => (line.startsWith("0x") ? line : `0x${line}`));
}

function getPrivateKey() {
  const envKey = (process.env.BOT_PRIVATE_KEY || "").trim();
  if (envKey) return envKey.startsWith("0x") ? envKey : `0x${envKey}`;

  const keys = readKeys();
  if (keys.length === 0) throw new Error("BOT_PRIVATE_KEY is empty and keys.txt was not found or is empty");

  const rawIndex = (process.env.KEY_INDEX || "1").trim();
  const index = Number.parseInt(rawIndex, 10);
  if (!Number.isInteger(index) || index < 1 || index > keys.length) {
    throw new Error(`Invalid KEY_INDEX=${rawIndex} for ${keys.length} keys`);
  }
  return keys[index - 1];
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function requireAddress(value, label) {
  if (!ADDRESS_RE.test(value || "")) throw new Error(`${label} must be an EVM address`);
  return ethers.utils.getAddress(value);
}

function requestJson(url) {
  return new Promise((resolve, reject) => {
    https
      .get(url, { headers: { accept: "application/json" } }, (res) => {
        let data = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => {
          if (res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`GET ${url} failed: HTTP ${res.statusCode} ${data.slice(0, 300)}`));
            return;
          }
          try {
            resolve(JSON.parse(data));
          } catch (error) {
            reject(new Error(`Invalid JSON from ${url}: ${error.message}`));
          }
        });
      })
      .on("error", reject);
  });
}

function requestApiJson(method, route, body, token) {
  return new Promise((resolve, reject) => {
    const url = new URL(route.startsWith("http") ? route : `${API_BASE}${route}`);
    const payload = body == null ? null : JSON.stringify(body);
    const headers = { accept: "application/json" };
    if (payload) {
      headers["content-type"] = "application/json";
      headers["content-length"] = Buffer.byteLength(payload);
    }
    if (token) headers.authorization = `Bearer ${token}`;

    const req = https.request(url, { method, headers }, (res) => {
      let data = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        data += chunk;
      });
      res.on("end", () => {
        let parsed = null;
        if (data) {
          try {
            parsed = JSON.parse(data);
          } catch {
            parsed = data;
          }
        }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          const msg =
            parsed && typeof parsed === "object"
              ? parsed.error?.message || parsed.message || JSON.stringify(parsed)
              : data || `HTTP ${res.statusCode}`;
          const error = new Error(`${method} ${url.pathname} failed: HTTP ${res.statusCode} ${msg}`);
          error.statusCode = res.statusCode;
          error.responseBody = parsed;
          error.responseMessage = msg;
          reject(error);
          return;
        }
        resolve(parsed);
      });
    });
    req.on("error", reject);
    if (payload) req.write(payload);
    req.end();
  });
}

async function loadSystemConfig() {
  const body = await requestJson(`${API_BASE}/system/config`);
  if (!body || !body.data) throw new Error("GET /system/config returned no data");
  return body.data;
}

function getProvider(parsed = {}) {
  const rpc = parsed.rpc || process.env.MIDAS_RPC_URL || process.env.EVM_RPC_URL || DEFAULT_RPC_URL;
  return new ethers.providers.JsonRpcProvider(rpc);
}

async function getSigner(parsed = {}) {
  const provider = getProvider(parsed);
  const wallet = new ethers.Wallet(getPrivateKey(), provider);
  const network = await provider.getNetwork();
  if (process.env.EVM_CHAIN_ID && Number(process.env.EVM_CHAIN_ID) !== network.chainId) {
    throw new Error(`Wrong chain id: got ${network.chainId}, expected ${process.env.EVM_CHAIN_ID}`);
  }
  log("INFO", `RPC chain id: ${network.chainId}`);
  log("INFO", `Wallet: ${wallet.address}`);
  return wallet;
}

function getWalletOnly() {
  const wallet = new ethers.Wallet(getPrivateKey());
  log("INFO", `Wallet: ${wallet.address}`);
  return wallet;
}

async function getNonceMessage(address) {
  const body = await requestApiJson("GET", `/auth/nonce?walletAddress=${encodeURIComponent(address)}`);
  if (!body || !body.success || !body.data || !body.data.message) {
    throw new Error(`Unexpected nonce response: ${JSON.stringify(body)}`);
  }
  return body.data.message;
}

async function getAuthToken(wallet) {
  const address = await wallet.getAddress();
  const existing = await requestApiJson("POST", "/auth/wallet", { walletAddress: address }).catch((error) => {
    log("WARNING", `Wallet auth check failed for ${address}: ${error.message}`);
    return null;
  });
  if (existing && existing.success && existing.data && existing.data.registered && existing.data.accessToken) {
    return existing.data.accessToken;
  }

  const message = await getNonceMessage(address);
  const signature = await wallet.signMessage(message);
  const displayName = `midas-${address.slice(-6).toLowerCase()}`;
  const registered = await requestApiJson("POST", "/auth/wallet/register", {
    walletAddress: address,
    signature,
    message,
    displayName,
  });
  if (!registered || !registered.success || !registered.data || !registered.data.accessToken) {
    throw new Error(`Unexpected register response: ${JSON.stringify(registered)}`);
  }
  return registered.data.accessToken;
}

async function requestFaucetForWallet(wallet, token) {
  const address = wallet.address;
  const route = token === "usdc" ? "/users/faucet_usdc" : "/users/faucet_native";
  const authToken = await getAuthToken(wallet);
  return requestApiJson("POST", route, { walletAddress: address }, authToken);
}

async function getQuestStatus(authToken) {
  const body = await requestApiJson("GET", "/quests/status", null, authToken);
  if (!body || !body.success || !body.data) {
    throw new Error(`Unexpected quest status response: ${JSON.stringify(body)}`);
  }
  return body.data;
}

function flattenQuests(statusBody) {
  return [
    ...(statusBody.dailyQuests || []),
    ...(statusBody.weeklyQuests || []),
    ...(statusBody.milestoneQuests || []),
    ...(statusBody.campaignQuests || []),
  ];
}

async function startQuest(authToken, questId) {
  return requestApiJson("POST", "/quests/start", { questId }, authToken);
}

async function claimQuest(authToken, questId) {
  return requestApiJson("POST", "/quests/claim", { questId }, authToken);
}

async function getUserPositions(walletAddress, status, authToken) {
  const qs = new URLSearchParams({ wallet: walletAddress });
  if (status) qs.set("status", status);
  const body = await requestApiJson("GET", `/users/positions?${qs.toString()}`, null, authToken);
  if (!body || !body.success || !body.data) {
    throw new Error(`Unexpected positions response: ${JSON.stringify(body)}`);
  }
  return Array.isArray(body.data.positions) ? body.data.positions : [];
}

async function activateRewardQuestsForWallet(wallet) {
  const authToken = await getAuthToken(wallet);
  const status = await getQuestStatus(authToken);
  const quests = flattenQuests(status);
  const startable = quests.filter((quest) => String(quest.status || "").toUpperCase() === "LOCKED");
  const claimable = quests.filter((quest) => String(quest.status || "").toUpperCase() === "CLAIMABLE");

  log("INFO", `Reward quests: total=${quests.length}, startable=${startable.length}, claimable=${claimable.length}`);
  for (const quest of startable) {
    try {
      const res = await startQuest(authToken, quest.id);
      log("INFO", `Quest start OK: ${quest.title || quest.id} | ${JSON.stringify(res)}`);
    } catch (error) {
      log("WARNING", `Quest start failed: ${quest.title || quest.id} | ${error.message || error}`);
    }
  }
  for (const quest of claimable) {
    try {
      const res = await claimQuest(authToken, quest.id);
      log("INFO", `Quest claim OK: ${quest.title || quest.id} | ${JSON.stringify(res)}`);
    } catch (error) {
      log("WARNING", `Quest claim failed: ${quest.title || quest.id} | ${error.message || error}`);
    }
  }
  return authToken;
}

async function claimRewardQuestsForWallet(authToken) {
  const status = await getQuestStatus(authToken);
  const claimable = flattenQuests(status).filter((quest) => String(quest.status || "").toUpperCase() === "CLAIMABLE");
  log("INFO", `Reward quests claimable after trades: ${claimable.length}`);
  for (const quest of claimable) {
    try {
      const res = await claimQuest(authToken, quest.id);
      log("INFO", `Quest claim OK: ${quest.title || quest.id} | ${JSON.stringify(res)}`);
    } catch (error) {
      log("WARNING", `Quest claim failed: ${quest.title || quest.id} | ${error.message || error}`);
    }
  }
}

async function getCheckedProvider(parsed) {
  const provider = getProvider(parsed);
  const network = await provider.getNetwork();
  if (process.env.EVM_CHAIN_ID && Number(process.env.EVM_CHAIN_ID) !== network.chainId) {
    throw new Error(`Wrong chain id: got ${network.chainId}, expected ${process.env.EVM_CHAIN_ID}`);
  }
  log("INFO", `RPC chain id: ${network.chainId}`);
  return provider;
}

function getMarketContract(address, signerOrProvider) {
  return new ethers.Contract(address, MIDAS_MARKET_ABI, signerOrProvider);
}

async function assertContractCode(provider, address) {
  const code = await provider.getCode(address);
  if (!code || code === "0x") {
    const rpcUrl = provider.connection && provider.connection.url ? provider.connection.url : "selected RPC";
    throw new Error(
      `No contract code at ${address} on ${rpcUrl}. ` +
        `Use LitEVM/LiteForge RPC, for example: ${DEFAULT_RPC_URL}`
    );
  }
}

function findCollateral(sysCfg, address) {
  const lower = address.toLowerCase();
  const item = (sysCfg.collateralTokens || []).find((token) => token.address.toLowerCase() === lower);
  if (!item) throw new Error(`Collateral ${address} not found in /system/config`);
  return item;
}

function findPreferredUsdcCollateral(sysCfg) {
  const tokens = sysCfg.collateralTokens || [];
  return (
    tokens.find((token) => /^usdc(?:\.e)?$/i.test(String(token.symbol || ""))) ||
    tokens.find((token) => String(token.symbol || "").toLowerCase().includes("usdc")) ||
    null
  );
}

function defaultToUsdcCollateral(parsed, sysCfg) {
  if (parsed.collateral) return;
  const usdc = findPreferredUsdcCollateral(sysCfg);
  if (!usdc) return;
  parsed.collateral = usdc.address;
  log("INFO", `Default collateral filter: ${usdc.symbol || "USDC"} ${usdc.address}`);
}

function isNativeCollateral(sysCfg, collateralToken) {
  return !!sysCfg.nativeWrapper && collateralToken.toLowerCase() === sysCfg.nativeWrapper.toLowerCase();
}

function effectiveProtocolFeeBps(sysCfg, marketData) {
  return marketData.overrideProtocolFeeBps
    ? ethers.BigNumber.from(marketData.protocolFeeBpsOverride)
    : ethers.BigNumber.from(sysCfg.fees.protocolFeeBps);
}

function applyBuyFees(base, marketData, sysCfg) {
  const creatorFee = base.mul(marketData.creatorFeeBps).div(BPS);
  const protocolFee = base.mul(effectiveProtocolFeeBps(sysCfg, marketData)).div(BPS);
  const userFees = creatorFee.mul(sysCfg.fees.userFeeBps).div(BPS);
  return {
    creatorFee,
    protocolFee,
    userFees,
    total: base.add(creatorFee).add(protocolFee).add(userFees),
  };
}

function applySellFees(base, marketData, sysCfg) {
  const creatorFee = base.mul(marketData.creatorFeeBps).div(BPS);
  const protocolFee = base.mul(effectiveProtocolFeeBps(sysCfg, marketData)).div(BPS);
  const userFees = creatorFee.mul(sysCfg.fees.userFeeBps).div(BPS);
  return {
    creatorFee,
    protocolFee,
    userFees,
    total: base.sub(creatorFee).sub(protocolFee).sub(userFees),
  };
}

function withSlippageUp(value, slippageBps) {
  return value.add(value.mul(slippageBps).div(BPS));
}

function withSlippageDown(value, slippageBps) {
  return value.sub(value.mul(slippageBps).div(BPS));
}

function decimalPlaces(value) {
  const text = String(value || "");
  return text.includes(".") ? text.split(".", 2)[1].length : 0;
}

function decimalToScaledBigInt(value, scale) {
  const text = String(value || "").trim();
  if (!/^\d+(?:\.\d+)?$/.test(text)) throw new Error(`Invalid decimal amount: ${value}`);
  const [whole, fraction = ""] = text.split(".");
  return BigInt(whole + fraction.padEnd(scale, "0").slice(0, scale));
}

function percentToBps(value, label) {
  const text = String(value || "").trim().replace(/%$/, "");
  const scaled = decimalToScaledBigInt(text, 2);
  if (scaled <= 0n) throw new Error(`${label} must be > 0`);
  if (scaled > 10_000n) throw new Error(`${label} must be <= 100`);
  return Number(scaled);
}

function scaledBigIntToDecimal(value, scale) {
  if (scale === 0) return value.toString();
  const negative = value < 0n;
  const abs = negative ? -value : value;
  const raw = abs.toString().padStart(scale + 1, "0");
  const whole = raw.slice(0, -scale);
  const fraction = raw.slice(-scale).replace(/0+$/, "");
  return `${negative ? "-" : ""}${whole}${fraction ? `.${fraction}` : ""}`;
}

function randomIntInclusive(maxExclusive) {
  if (maxExclusive <= 0) throw new Error("Invalid random range");
  return Math.floor(Math.random() * maxExclusive);
}

function randomIntRangeInclusive(min, max) {
  if (!Number.isInteger(min) || !Number.isInteger(max) || min < 1 || max < min) {
    throw new Error(`Invalid count range: ${min}..${max}`);
  }
  return min + Math.floor(Math.random() * (max - min + 1));
}

function randomDecimalInRange(minRaw, maxRaw) {
  const scale = Math.max(decimalPlaces(minRaw), decimalPlaces(maxRaw));
  const min = decimalToScaledBigInt(minRaw, scale);
  const max = decimalToScaledBigInt(maxRaw, scale);
  if (min <= 0n) throw new Error("--amount-min must be > 0");
  if (max < min) throw new Error("--amount-max must be >= --amount-min");
  const span = max - min + 1n;
  const picked = min + BigInt(Math.floor(Math.random() * Number(span)));
  return scaledBigIntToDecimal(picked, scale);
}

function randomPercentBps(minPercent, maxPercent) {
  const min = Math.round(minPercent * 100);
  const max = Math.round(maxPercent * 100);
  return min + randomIntInclusive(max - min + 1);
}

async function findShareAmountForBaseTarget(market, outcomes, targetBase, decimals) {
  const oneShare = ethers.utils.parseUnits("1", decimals);
  let low = ethers.BigNumber.from(0);
  let high = targetBase.gt(oneShare) ? targetBase : oneShare;
  let quote = await market.getOutcomePurchaseCost(outcomes, [high]);

  for (let attempt = 0; attempt < 40 && quote.lt(targetBase); attempt += 1) {
    low = high;
    high = high.mul(2);
    quote = await market.getOutcomePurchaseCost(outcomes, [high]);
  }
  if (quote.lt(targetBase)) throw new Error(`Could not size shares for target base=${targetBase.toString()}`);

  for (let attempt = 0; attempt < 10; attempt += 1) {
    const mid = low.add(high).div(2);
    if (mid.lte(low)) break;
    const midQuote = await market.getOutcomePurchaseCost(outcomes, [mid]);
    if (midQuote.eq(targetBase)) return mid;
    if (midQuote.lt(targetBase)) low = mid;
    else high = mid;
  }
  return high;
}

async function findShareAmountLikeFrontend(providerOrSigner, market, marketAddress, outcome, targetBase, minBase, decimals) {
  const helperInput = targetBase.eq(minBase) ? targetBase.add(ethers.BigNumber.from(10_000)) : targetBase;
  try {
    const helper = new ethers.Contract(MIDAS_MARKET_HELPER, MIDAS_MARKET_HELPER_ABI, providerOrSigner);
    const shares = await helper.getSharesForCollateralInMarket(marketAddress, outcome, helperInput);
    if (shares.gt(0)) return shares;
    log("WARNING", "Midas helper returned zero shares; falling back to local sizing");
  } catch (error) {
    log("WARNING", `Midas helper sizing failed; falling back to local sizing: ${error.message || error}`);
  }
  return findShareAmountForBaseTarget(market, [outcome], targetBase, decimals);
}

function shuffle(items) {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = randomIntInclusive(i + 1);
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function uniqueByAddress(items) {
  const seen = new Set();
  const result = [];
  for (const item of items) {
    const key = item.address.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      result.push(item);
    }
  }
  return result;
}

function ensureCommand(parsed, allowed) {
  if (!parsed.command || !allowed.includes(parsed.command)) {
    usage();
    process.exit(parsed.command ? 1 : 0);
  }
}

function statusName(status) {
  const names = ["PENDING", "CANCELLED", "ACTIVE", "PAUSED", "RESOLVED", "CLOSED", "UPDATE_REQUIRED", "VOIDED", "VOIDED_CLOSED"];
  const numeric = Number(status);
  return Number.isInteger(numeric) && names[numeric] ? `${names[numeric]} (${numeric})` : String(status || "unknown");
}

function formatDateLike(value) {
  if (value == null || value === "") return "unknown";
  if (/^\d+$/.test(String(value))) {
    const n = Number(value);
    return new Date((n > 10_000_000_000 ? n : n * 1000)).toISOString();
  }
  const ts = Date.parse(value);
  return Number.isNaN(ts) ? String(value) : new Date(ts).toISOString();
}

function shortText(value, max = 220) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max - 3)}...` : text;
}

function extractRevertSelector(error) {
  const candidates = [
    error?.data,
    error?.error?.data,
    error?.error?.error?.data,
    error?.receipt?.revertReason,
    error?.reason,
    error?.message,
  ];
  const text = candidates.filter(Boolean).join(" ");
  const match = text.match(/0x[0-9a-fA-F]{8}/);
  return match ? match[0].toLowerCase() : "";
}

function isCostExceedsMaximum(error) {
  return extractRevertSelector(error) === "0xd5b9787a";
}

async function showSystem() {
  const sysCfg = await loadSystemConfig();
  log("INFO", `Platform paused: ${Boolean(sysCfg.paused)}`);
  log("INFO", `Protocol fee bps: ${sysCfg.fees && sysCfg.fees.protocolFeeBps}`);
  log("INFO", `User fee bps: ${sysCfg.fees && sysCfg.fees.userFeeBps}`);
  log("INFO", `Native wrapper: ${sysCfg.nativeWrapper || "not configured"}`);
  for (const token of sysCfg.collateralTokens || []) {
    log(
      "INFO",
      `Collateral ${token.symbol || ""} ${token.address} decimals=${token.decimals} min=${token.config.minTradeSizeInCollateral} max=${token.config.maxTradeSizeInCollateral}`
    );
  }
}

async function listStandard(parsed) {
  const items = await fetchStandardMarkets(parsed);
  log("INFO", `Standard open markets: ${items.length}`);
  for (const item of items) {
    const title = item.title || item.question || "";
    log("INFO", `${item.market} | outcomes=${item.outcomeCount} | collateral=${item.collateralToken} | ${title}`);
  }
}

async function fetchStandardMarkets(parsed) {
  const qs = new URLSearchParams({ status: "open", limit: String(parsed.limit || 20) });
  if (parsed.collateral) qs.set("collateralToken", requireAddress(parsed.collateral, "collateral"));
  const body = await requestJson(`${API_BASE}/markets?${qs.toString()}`);
  return (body.data && body.data.items) || [];
}

function printStandardMarket(item) {
  log("INFO", `Market: ${item.market}`);
  log("INFO", `Title: ${item.title || item.question || "unknown"}`);
  log("INFO", `Status: ${item.status || "unknown"} | outcomes=${item.outcomeCount} | category=${item.category || "unknown"}`);
  log("INFO", `Collateral: ${item.collateralToken || "unknown"} | creatorFeeBps=${item.creatorFeeBps || "unknown"}`);
  log("INFO", `Window: ${formatDateLike(item.startsAt)} -> ${formatDateLike(item.expiresAt)}`);
  if (item.slug) log("INFO", `Slug: ${item.slug}`);
  if (item.description) log("INFO", `Description: ${shortText(item.description)}`);
  if (item.rulesDescription) log("INFO", `Rules: ${shortText(item.rulesDescription)}`);
  if (Array.isArray(item.outcomes)) {
    for (const outcome of item.outcomes) {
      log("INFO", `Outcome ${outcome.id}: ${outcome.title || outcome.name || ""}`);
    }
  }
}

function printQuickMarket(item) {
  log("INFO", `Quick market: ${item.marketAddress}`);
  log("INFO", `Asset: ${item.asset} | cycle=${item.cycleDurationMin}m | status=${item.status}`);
  log("INFO", `Strike: ${item.strikePrice || "unknown"} | winner=${item.winner || "unknown"}`);
  log("INFO", `Window: ${formatDateLike(item.startsAt)} -> ${formatDateLike(item.expiresAt)}`);
  if (item.market) {
    log("INFO", `Nested market status: ${item.market.status || "unknown"} | volume=${item.market.volume || "unknown"} | tvl=${item.market.tvl || "unknown"}`);
  }
}

async function findStandardMarket(address) {
  for (const status of ["open", "closed"]) {
    for (let page = 1; page <= 5; page += 1) {
      const qs = new URLSearchParams({ status, limit: "100", page: String(page) });
      const body = await requestJson(`${API_BASE}/markets?${qs.toString()}`);
      const items = (body.data && body.data.items) || [];
      const found = items.find((item) => item.market && item.market.toLowerCase() === address.toLowerCase());
      if (found) return found;
      if (items.length < 100) break;
    }
  }
  return null;
}

async function findQuickMarket(address) {
  const queries = [
    new URLSearchParams({ bucket: "live", limit: "100" }),
    new URLSearchParams({ limit: "100", window: "30d" }),
  ];
  for (const qs of queries) {
    const body = await requestJson(`${API_BASE}/daily-markets?${qs.toString()}`);
    const items = (body.data && body.data.items) || [];
    const found = items.find((item) => item.marketAddress && item.marketAddress.toLowerCase() === address.toLowerCase());
    if (found) return found;
  }
  return null;
}

async function showMarket(parsed) {
  const marketAddress = requireAddress(parsed.market, "market");
  const standard = await findStandardMarket(marketAddress);
  if (standard) {
    log("INFO", "Source: standard markets API");
    printStandardMarket(standard);
    return;
  }

  const quick = await findQuickMarket(marketAddress);
  if (quick) {
    log("INFO", "Source: quick markets API");
    printQuickMarket(quick);
    return;
  }

  throw new Error(`Market ${marketAddress} was not found in API open/closed/live lists`);
}

async function listQuick(parsed) {
  const items = await fetchQuickMarkets(parsed);
  log("INFO", `Quick live markets: ${items.length}`);
  for (const item of items) {
    log(
      "INFO",
      `${item.marketAddress} | ${item.asset} ${item.cycleDurationMin}m | strike=${item.strikePrice} | ${item.startsAt} -> ${item.expiresAt}`
    );
  }
}

async function fetchQuickMarkets(parsed) {
  const qs = new URLSearchParams({ bucket: "live", limit: String(parsed.limit || 100) });
  if (parsed.asset) qs.set("asset", parsed.asset);
  const body = await requestJson(`${API_BASE}/daily-markets?${qs.toString()}`);
  const now = Date.now();
  return ((body.data && body.data.items) || []).filter((item) => {
    if (!item.marketAddress) return false;
    if (parsed.cycle != null && Number(item.cycleDurationMin) !== parsed.cycle) return false;
    return Date.parse(item.startsAt) <= now && Date.parse(item.expiresAt) > now;
  });
}

async function validateActiveMarket(market) {
  const status = Number(await market.getStatus());
  if (status !== 2) throw new Error(`Market is not ACTIVE: status=${status}`);

  const marketData = await market.getMarket();
  const now = Math.floor(Date.now() / 1000);
  if (now < Number(marketData.startsAt)) throw new Error("Market is pre-window");
  if (now >= Number(marketData.expiresAt)) throw new Error("Market is expired");
  return marketData;
}

async function doBuy(parsed) {
  const marketAddress = requireAddress(parsed.market, "market");
  if (!Number.isInteger(parsed.outcome) || parsed.outcome < 0) throw new Error("--outcome is required");
  if (!parsed.amount && !parsed.targetBaseAmount && !parsed.targetSpendAmount) throw new Error("--amount is required");

  const sysCfg = await loadSystemConfig();
  if (sysCfg.paused) throw new Error("Platform is paused");
  const signerOrProvider = parsed.send ? await getSigner(parsed) : await getCheckedProvider(parsed);
  await assertContractCode(parsed.send ? signerOrProvider.provider : signerOrProvider, marketAddress);
  const market = getMarketContract(marketAddress, signerOrProvider);
  const marketData = await validateActiveMarket(market);
  const collateralInfo = findCollateral(sysCfg, marketData.collateralToken);
  const decimals = Number(collateralInfo.decimals);
  const outcomes = [parsed.outcome];
  const minBase = ethers.BigNumber.from(collateralInfo.config.minTradeSizeInCollateral);
  const maxBase = ethers.BigNumber.from(collateralInfo.config.maxTradeSizeInCollateral);
  const nativeCollateral = isNativeCollateral(sysCfg, collateralInfo.address);
  if (parsed.usdcPercentSizing) {
    const symbol = String(collateralInfo.symbol || "").toLowerCase();
    if (!symbol.includes("usdc")) {
      throw new Error(`USDC percent mode picked non-USDC market: ${collateralInfo.symbol || collateralInfo.address}`);
    }
  }
  let finalAmount;
  let targetBase = null;
  let targetSpend = null;
  if (parsed.targetBaseAmount || parsed.targetSpendAmount) {
    if (nativeCollateral && parsed.nativePercentSizing && parsed.send) {
      const nativeBalance = await signerOrProvider.provider.getBalance(signerOrProvider.address);
      const pctBps = randomPercentBps(10, 30);
      targetBase = nativeBalance.mul(pctBps).div(10_000);
      log(
        "INFO",
        `Native zkLTC sizing: ${ethers.utils.formatUnits(nativeBalance, decimals)} balance * ${(pctBps / 100).toFixed(2)}% = ${ethers.utils.formatUnits(targetBase, decimals)} ${collateralInfo.symbol}`
      );
    } else if (parsed.targetSpendAmount) {
      targetSpend = ethers.utils.parseUnits(parsed.targetSpendAmount, decimals);
      const creatorFeeBps = ethers.BigNumber.from(marketData.creatorFeeBps);
      const protocolFeeBps = effectiveProtocolFeeBps(sysCfg, marketData);
      const userFeeOnCreatorBps = creatorFeeBps.mul(sysCfg.fees.userFeeBps).div(BPS);
      const totalFeeBps = creatorFeeBps.add(protocolFeeBps).add(userFeeOnCreatorBps);
      targetBase = targetSpend.mul(BPS).div(BPS.add(totalFeeBps));
    } else {
      targetBase = ethers.utils.parseUnits(parsed.targetBaseAmount, decimals);
    }
    if (parsed.autoMinTrade && targetBase.lt(minBase)) targetBase = minBase;
    if (nativeCollateral && parsed.nativePercentSizing && targetBase.gt(maxBase)) targetBase = maxBase;
    if (targetBase.gt(maxBase)) throw new Error(`Target trade too large: target=${targetBase.toString()} max=${maxBase.toString()}`);
    finalAmount = await findShareAmountLikeFrontend(
      signerOrProvider,
      market,
      marketAddress,
      parsed.outcome,
      targetBase,
      minBase,
      decimals
    );
    parsed.amount = ethers.utils.formatUnits(finalAmount, decimals);
  } else {
    finalAmount = ethers.utils.parseUnits(parsed.amount, decimals);
  }
  let amounts = [finalAmount];

  let base = await market.getOutcomePurchaseCost(outcomes, amounts);
  if (parsed.autoMinTrade && base.gt(0) && base.lt(minBase)) {
    for (let attempt = 1; attempt <= 5 && base.lt(minBase); attempt += 1) {
      const adjusted = finalAmount.mul(minBase).mul(105).div(base.mul(100)).add(1);
      finalAmount = adjusted.gt(finalAmount) ? adjusted : finalAmount.add(1);
      amounts = [finalAmount];
      base = await market.getOutcomePurchaseCost(outcomes, amounts);
    }
    parsed.amount = ethers.utils.formatUnits(finalAmount, decimals);
    log("INFO", `Auto-adjusted shares to meet min trade: ${parsed.amount}`);
  }
  if (base.lt(minBase)) throw new Error(`Trade too small: base=${base.toString()} min=${minBase.toString()}`);
  if (base.gt(maxBase)) throw new Error(`Trade too large: base=${base.toString()} max=${maxBase.toString()}`);

  let fees = applyBuyFees(base, marketData, sysCfg);
  let maxCost = withSlippageUp(fees.total, parsed.slippageBps);
  log("INFO", `Buy market: ${marketAddress}`);
  if (targetSpend) log("INFO", `Target spend budget: ${ethers.utils.formatUnits(targetSpend, decimals)} ${collateralInfo.symbol}`);
  if (targetBase) log("INFO", `Target base amount: ${ethers.utils.formatUnits(targetBase, decimals)} ${collateralInfo.symbol}`);
  log("INFO", `Outcome: ${parsed.outcome}, shares: ${parsed.amount}`);
  log("INFO", `Base quote: ${ethers.utils.formatUnits(base, decimals)} ${collateralInfo.symbol}`);
  log("INFO", `Fee-adjusted cost: ${ethers.utils.formatUnits(fees.total, decimals)} ${collateralInfo.symbol}`);
  log("INFO", `Max cost with slippage: ${ethers.utils.formatUnits(maxCost, decimals)} ${collateralInfo.symbol}`);

  if (!parsed.send) {
    log("INFO", "Dry-run only. Add --send to submit.");
    return { sent: false, market: marketAddress, outcome: parsed.outcome, amount: parsed.amount };
  }

  async function refreshQuoteBeforeSend() {
    const freshBase = await market.getOutcomePurchaseCost(outcomes, amounts);
    if (freshBase.lt(minBase)) throw new Error(`Trade too small after re-quote: base=${freshBase.toString()} min=${minBase.toString()}`);
    if (freshBase.gt(maxBase)) throw new Error(`Trade too large after re-quote: base=${freshBase.toString()} max=${maxBase.toString()}`);
    const freshFees = applyBuyFees(freshBase, marketData, sysCfg);
    const freshMaxCost = withSlippageUp(freshFees.total, parsed.slippageBps);
    if (!freshMaxCost.eq(maxCost)) {
      base = freshBase;
      fees = freshFees;
      maxCost = freshMaxCost;
      log(
        "INFO",
        `Re-quoted before buy: base=${ethers.utils.formatUnits(base, decimals)} ${collateralInfo.symbol}, ` +
          `fee-adjusted=${ethers.utils.formatUnits(fees.total, decimals)} ${collateralInfo.symbol}, ` +
          `maxCost=${ethers.utils.formatUnits(maxCost, decimals)} ${collateralInfo.symbol}`
      );
    }
  }

  let tx;
  if (nativeCollateral) {
    let nativeBalance = await signerOrProvider.provider.getBalance(signerOrProvider.address);
    if (nativeBalance.lt(maxCost)) {
      log(
        "WARNING",
        `Native balance low: have ${ethers.utils.formatUnits(nativeBalance, decimals)} ${collateralInfo.symbol}, need ${ethers.utils.formatUnits(maxCost, decimals)}. Requesting zkLTC faucet...`
      );
      try {
        const faucetRes = await requestFaucetForWallet(signerOrProvider, "zkltc");
        log("INFO", `Faucet zkltc response: ${JSON.stringify(faucetRes)}`);
        await sleep(8000);
        nativeBalance = await signerOrProvider.provider.getBalance(signerOrProvider.address);
      } catch (error) {
        log("WARNING", `Faucet zkltc failed: ${error.message || error}`);
      }
      if (nativeBalance.lt(maxCost)) {
        throw new Error(
          `Insufficient native balance after faucet: have ${ethers.utils.formatUnits(nativeBalance, decimals)} ${collateralInfo.symbol}, need ${ethers.utils.formatUnits(maxCost, decimals)}`
        );
      }
    }
    await refreshQuoteBeforeSend();
    nativeBalance = await signerOrProvider.provider.getBalance(signerOrProvider.address);
    if (nativeBalance.lt(maxCost)) {
      throw new Error(
        `Insufficient native balance after re-quote: have ${ethers.utils.formatUnits(nativeBalance, decimals)} ${collateralInfo.symbol}, need ${ethers.utils.formatUnits(maxCost, decimals)}`
      );
    }
    try {
      tx = await market.buy(outcomes, amounts, maxCost, { value: maxCost });
    } catch (error) {
      if (!isCostExceedsMaximum(error)) throw error;
      log("WARNING", "Buy reverted with CostExceedsMaximum; re-quoting once and retrying");
      await refreshQuoteBeforeSend();
      nativeBalance = await signerOrProvider.provider.getBalance(signerOrProvider.address);
      if (nativeBalance.lt(maxCost)) {
        throw new Error(
          `Insufficient native balance after retry re-quote: have ${ethers.utils.formatUnits(nativeBalance, decimals)} ${collateralInfo.symbol}, need ${ethers.utils.formatUnits(maxCost, decimals)}`
        );
      }
      tx = await market.buy(outcomes, amounts, maxCost, { value: maxCost });
    }
  } else {
    const erc20 = new ethers.Contract(collateralInfo.address, ERC20_ABI, signerOrProvider);
    let tokenBalance = await erc20.balanceOf(signerOrProvider.address);
    if (tokenBalance.lt(maxCost)) {
      log(
        "WARNING",
        `${collateralInfo.symbol} balance low: have ${ethers.utils.formatUnits(tokenBalance, decimals)}, need ${ethers.utils.formatUnits(maxCost, decimals)}. Requesting faucet...`
      );
      if (!String(collateralInfo.symbol || "").toLowerCase().includes("usdc")) {
        throw new Error(`No faucet route configured for collateral ${collateralInfo.symbol || collateralInfo.address}`);
      }
      try {
        const faucetRes = await requestFaucetForWallet(signerOrProvider, "usdc");
        log("INFO", `Faucet usdc response: ${JSON.stringify(faucetRes)}`);
        await sleep(8000);
        tokenBalance = await erc20.balanceOf(signerOrProvider.address);
      } catch (error) {
        log("WARNING", `Faucet usdc failed: ${error.message || error}`);
      }
      if (tokenBalance.lt(maxCost)) {
        throw new Error(
          `Insufficient ${collateralInfo.symbol} balance after faucet: have ${ethers.utils.formatUnits(tokenBalance, decimals)}, need ${ethers.utils.formatUnits(maxCost, decimals)}`
        );
      }
    }
    const allowance = await erc20.allowance(signerOrProvider.address, marketAddress);
    if (allowance.lt(maxCost)) {
      const approveTx = await erc20.approve(marketAddress, maxCost);
      log("INFO", `Approve tx sent: ${approveTx.hash}`);
      await approveTx.wait();
    }
    await refreshQuoteBeforeSend();
    tokenBalance = await erc20.balanceOf(signerOrProvider.address);
    if (tokenBalance.lt(maxCost)) {
      throw new Error(
        `Insufficient ${collateralInfo.symbol} balance after re-quote: have ${ethers.utils.formatUnits(tokenBalance, decimals)}, need ${ethers.utils.formatUnits(maxCost, decimals)}`
      );
    }
    const freshAllowance = await erc20.allowance(signerOrProvider.address, marketAddress);
    if (freshAllowance.lt(maxCost)) {
      const approveTx = await erc20.approve(marketAddress, maxCost);
      log("INFO", `Approve top-up tx sent: ${approveTx.hash}`);
      await approveTx.wait();
    }
    try {
      tx = await market.buy(outcomes, amounts, maxCost);
    } catch (error) {
      if (!isCostExceedsMaximum(error)) throw error;
      log("WARNING", "Buy reverted with CostExceedsMaximum; re-quoting once and retrying");
      await refreshQuoteBeforeSend();
      tokenBalance = await erc20.balanceOf(signerOrProvider.address);
      if (tokenBalance.lt(maxCost)) {
        throw new Error(
          `Insufficient ${collateralInfo.symbol} balance after retry re-quote: have ${ethers.utils.formatUnits(tokenBalance, decimals)}, need ${ethers.utils.formatUnits(maxCost, decimals)}`
        );
      }
      const retryAllowance = await erc20.allowance(signerOrProvider.address, marketAddress);
      if (retryAllowance.lt(maxCost)) {
        const approveTx = await erc20.approve(marketAddress, maxCost);
        log("INFO", `Approve retry top-up tx sent: ${approveTx.hash}`);
        await approveTx.wait();
      }
      tx = await market.buy(outcomes, amounts, maxCost);
    }
  }
  log("INFO", `Buy tx sent: ${tx.hash}`);
  const receipt = await tx.wait();
  log("INFO", `Buy receipt status: ${receipt.status}`);
  return { sent: true, txHash: tx.hash, status: receipt.status, market: marketAddress, outcome: parsed.outcome, amount: parsed.amount };
}

async function runRandomBuyPlan(parsed, plan) {
  let fixedTargetBaseAmount = null;
  if (parsed.usdcPercent) {
    if (!parsed.send) throw new Error("--usdc-percent requires --send");
    const percentBps = percentToBps(parsed.usdcPercent, "--usdc-percent");
    const sysCfg = await loadSystemConfig();
    const usdc = findPreferredUsdcCollateral(sysCfg);
    if (!usdc) throw new Error("USDC collateral was not found in /system/config");
    parsed.collateral = usdc.address;
    const signer = await getSigner(parsed);
    const erc20 = new ethers.Contract(usdc.address, ERC20_ABI, signer);
    const balance = await erc20.balanceOf(signer.address);
    const perBet = balance.mul(percentBps).div(10_000).div(plan.length);
    if (perBet.lte(0)) throw new Error(`USDC percent amount is zero: balance=${balance.toString()}, percent=${parsed.usdcPercent}`);
    fixedTargetBaseAmount = ethers.utils.formatUnits(perBet, Number(usdc.decimals));
    log(
      "INFO",
      `USDC percent sizing: start balance=${ethers.utils.formatUnits(balance, Number(usdc.decimals))} ${usdc.symbol || "USDC"}, ` +
        `total=${parsed.usdcPercent}%, bets=${plan.length}, per bet budget=${fixedTargetBaseAmount} ${usdc.symbol || "USDC"}`
    );
  }

  let successCount = 0;
  for (let i = 0; i < plan.length; i += 1) {
    const picked = plan[i];
    const outcome =
      Number.isInteger(parsed.outcome) && parsed.outcome >= 0
        ? parsed.outcome
        : randomIntInclusive(Math.max(1, picked.outcomeCount));
    const targetBaseAmount = fixedTargetBaseAmount || randomDecimalInRange(parsed.amountMin, parsed.amountMax);
    log(
      "INFO",
      `[random ${i + 1}/${plan.length}] ${picked.source}${picked.boosted ? " boosted" : ""} ${picked.address} | outcome=${outcome} | ${fixedTargetBaseAmount ? "budget" : "target"}=${targetBaseAmount} collateral | ${shortText(picked.title, 120)}`
    );
    try {
      await doBuy({
        ...parsed,
        market: picked.address,
        outcome,
        targetBaseAmount: fixedTargetBaseAmount ? undefined : targetBaseAmount,
        targetSpendAmount: fixedTargetBaseAmount || undefined,
        nativePercentSizing: !fixedTargetBaseAmount,
        usdcPercentSizing: !!fixedTargetBaseAmount,
      });
      successCount += 1;
    } catch (error) {
      log("ERROR", `[random ${i + 1}/${plan.length}] buy failed: ${error.message || error}`);
    }
  }
  if (successCount === 0) throw new Error("No random buys completed");
  log("INFO", `Random buys completed: ${successCount}/${plan.length}`);
}

async function doRandomBuy(parsed) {
  if (!parsed.usdcPercent && (!parsed.amountMin || !parsed.amountMax)) throw new Error("--amount-min and --amount-max are required");
  if (parsed.usdcPercent) percentToBps(parsed.usdcPercent, "--usdc-percent");
  if (parsed.countMin != null || parsed.countMax != null) {
    if (!Number.isInteger(parsed.countMin) || !Number.isInteger(parsed.countMax)) throw new Error("--count-min and --count-max are required together");
    parsed.count = randomIntRangeInclusive(parsed.countMin, parsed.countMax);
    log("INFO", `Random bet count picked: ${parsed.count} from range ${parsed.countMin}..${parsed.countMax}`);
  }
  if (!Number.isInteger(parsed.count) || parsed.count < 1) throw new Error("--count must be >= 1");
  if (!["standard", "quick", "all"].includes(parsed.source)) throw new Error("--source must be standard, quick, or all");

  const sysCfg = await loadSystemConfig();
  if (parsed.source === "standard" || parsed.source === "all") defaultToUsdcCollateral(parsed, sysCfg);

  const markets = [];
  if (parsed.source === "standard" || parsed.source === "all") {
    const standard = await fetchStandardMarkets(parsed);
    for (const item of standard) {
      if (item.market) {
        markets.push({
          address: item.market,
          outcomeCount: Number(item.outcomeCount || 2),
          title: item.title || item.question || "standard market",
          source: "standard",
          boosted: Boolean(item.boosted),
        });
      }
    }
  }
  if (parsed.source === "quick" || parsed.source === "all") {
    const quick = await fetchQuickMarkets(parsed);
    for (const item of quick) {
      if (item.marketAddress) {
        markets.push({
          address: item.marketAddress,
          outcomeCount: 2,
          title: `${item.asset || "asset"} ${item.cycleDurationMin || "?"}m quick market`,
          source: "quick",
          boosted: false,
        });
      }
    }
  }
  if (parsed.boostedOnly) {
    for (let i = markets.length - 1; i >= 0; i -= 1) {
      if (!markets[i].boosted) markets.splice(i, 1);
    }
  }
  if (markets.length === 0) throw new Error(`No tradeable markets found for source=${parsed.source}`);

  log("INFO", `Random buy source=${parsed.source}, markets=${markets.length}, count=${parsed.count}`);
  if (parsed.usdcPercent) log("INFO", `Random USDC percent: ${parsed.usdcPercent}% total split across ${parsed.count} bets`);
  else log("INFO", `Random target base range: ${parsed.amountMin}..${parsed.amountMax} collateral`);
  const pool = parsed.uniqueMarkets ? uniqueByAddress(markets) : markets;
  if (parsed.uniqueMarkets && pool.length < parsed.count) throw new Error(`Not enough unique markets: need ${parsed.count}, have ${pool.length}`);
  const plan = parsed.uniqueMarkets ? shuffle(pool).slice(0, parsed.count) : Array.from({ length: parsed.count }, () => markets[randomIntInclusive(markets.length)]);
  await runRandomBuyPlan(parsed, plan);
}

async function doRewardTasks(parsed) {
  if (!parsed.usdcPercent && (!parsed.amountMin || !parsed.amountMax)) throw new Error("--amount-min and --amount-max are required");
  if (parsed.usdcPercent) percentToBps(parsed.usdcPercent, "--usdc-percent");
  parsed.source = "standard";
  parsed.limit = parsed.limit || 100;
  parsed.count = 3;
  const signer = await getSigner(parsed);
  const authToken = await activateRewardQuestsForWallet(signer);
  const sysCfg = await loadSystemConfig();
  defaultToUsdcCollateral(parsed, sysCfg);

  const standard = await fetchStandardMarkets(parsed);
  const markets = uniqueByAddress(
    standard
      .filter((item) => item.market)
      .map((item) => ({
        address: item.market,
        outcomeCount: Number(item.outcomeCount || 2),
        title: item.title || item.question || "standard market",
        source: "standard",
        boosted: Boolean(item.boosted),
      }))
  );
  const boosted = markets.filter((item) => item.boosted);
  if (boosted.length === 0) throw new Error("No boosted standard markets found");
  if (markets.length < 2) throw new Error("Need at least 2 different markets for reward tasks");

  const first = boosted[randomIntInclusive(boosted.length)];
  const rest = shuffle(markets.filter((item) => item.address.toLowerCase() !== first.address.toLowerCase()));
  const plan = [first, ...rest.slice(0, 2)];
  if (plan.length < 3) plan.push(markets[randomIntInclusive(markets.length)]);

  log("INFO", "Reward tasks plan:");
  log("INFO", "  - Make your first trade today");
  log("INFO", "  - Trade in 2 different markets");
  log("INFO", "  - Make 3 trades");
  log("INFO", "  - Trade in a boosted market");
  log("INFO", `Plan size: ${plan.length}; boosted market included: ${first.address}`);
  await runRandomBuyPlan(parsed, plan);
  await claimRewardQuestsForWallet(authToken);
}

async function doClaimRewardQuests() {
  const wallet = getWalletOnly();
  const authToken = await getAuthToken(wallet);
  await claimRewardQuestsForWallet(authToken);
}

function positionRawShares(position) {
  const value = position.netShares ?? position.shares;
  const text = String(value || "").trim();
  if (!/^\d+$/.test(text)) return ethers.BigNumber.from(0);
  return ethers.BigNumber.from(text);
}

function positionLabel(position, index) {
  const title = position.marketTitle || position.title || "untitled";
  return `[position ${index}] ${position.market} | outcome=${position.outcomeIndex} | ${title}`;
}

async function sellOutcomeShares(parsed, sysCfg, signerOrProvider, marketAddress, outcome, rawAmount, label) {
  const provider = signerOrProvider.provider || signerOrProvider;
  await assertContractCode(provider, marketAddress);
  const market = getMarketContract(marketAddress, signerOrProvider);
  let marketData;
  try {
    marketData = await validateActiveMarket(market);
  } catch (error) {
    log("WARNING", `${label} skipped: ${error.message || error}`);
    return "skipped";
  }
  const collateralInfo = findCollateral(sysCfg, marketData.collateralToken);
  const decimals = Number(collateralInfo.decimals);
  let amount = rawAmount;

  if (parsed.send) {
    const outcomeNftAddr = await market.MARKET_OUTCOME();
    await assertContractCode(provider, outcomeNftAddr);
    const nft = new ethers.Contract(outcomeNftAddr, ERC1155_ABI, provider);
    const tokenId = await nft.getTokenId(marketAddress, outcome);
    const balance = await nft.balanceOf(signerOrProvider.address, tokenId);
    log("INFO", `Share balance: ${ethers.utils.formatUnits(balance, decimals)}`);
    if (balance.isZero()) {
      log("WARNING", `${label} skipped: no outcome shares on wallet`);
      return "skipped";
    }
    if (balance.lt(amount)) {
      log("WARNING", `${label}: API shares exceed wallet balance, selling wallet balance instead`);
      amount = balance;
    }
  } else {
    log("INFO", "Dry-run sell quote only. Share balance check requires --send or BOT_PRIVATE_KEY.");
  }

  if (amount.lte(0)) {
    log("WARNING", `${label} skipped: zero shares`);
    return "skipped";
  }

  const outcomes = [outcome];
  const amounts = [amount];
  const base = await market.getOutcomeSaleReturn(outcomes, amounts);
  if (base.lte(0)) {
    log("WARNING", `${label} skipped: zero sell quote`);
    return "skipped";
  }
  const fees = applySellFees(base, marketData, sysCfg);
  if (fees.total.lte(0)) {
    log("WARNING", `${label} skipped: non-positive return after fees`);
    return "skipped";
  }
  const minReturn = withSlippageDown(fees.total, parsed.slippageBps);
  log("INFO", `Sell market: ${marketAddress}`);
  log("INFO", `Outcome: ${outcome}, shares: ${ethers.utils.formatUnits(amount, decimals)}`);
  log("INFO", `Base return: ${ethers.utils.formatUnits(base, decimals)} ${collateralInfo.symbol}`);
  log("INFO", `Net return: ${ethers.utils.formatUnits(fees.total, decimals)} ${collateralInfo.symbol}`);
  log("INFO", `Min return with slippage: ${ethers.utils.formatUnits(minReturn, decimals)} ${collateralInfo.symbol}`);

  if (!parsed.send) {
    log("INFO", "Dry-run only. Add --send to submit.");
    return "quoted";
  }

  const tx = await market.sell(outcomes, amounts, minReturn);
  log("INFO", `Sell tx sent: ${tx.hash}`);
  const receipt = await tx.wait();
  log("INFO", `Sell receipt status: ${receipt.status}`);
  return receipt.status === 1 ? "sold" : "failed";
}

async function doSell(parsed) {
  const marketAddress = requireAddress(parsed.market, "market");
  if (!Number.isInteger(parsed.outcome) || parsed.outcome < 0) throw new Error("--outcome is required");
  if (!parsed.amount) throw new Error("--amount is required");

  const sysCfg = await loadSystemConfig();
  if (sysCfg.paused) throw new Error("Platform is paused");
  const signerOrProvider = parsed.send ? await getSigner(parsed) : await getCheckedProvider(parsed);
  await assertContractCode(parsed.send ? signerOrProvider.provider : signerOrProvider, marketAddress);
  const market = getMarketContract(marketAddress, signerOrProvider);
  const marketData = await market.getMarket();
  const collateralInfo = findCollateral(sysCfg, marketData.collateralToken);
  const rawAmount = ethers.utils.parseUnits(parsed.amount, Number(collateralInfo.decimals));
  await sellOutcomeShares(parsed, sysCfg, signerOrProvider, marketAddress, parsed.outcome, rawAmount, "manual sell");
}

async function doSellAll(parsed) {
  const sysCfg = await loadSystemConfig();
  if (sysCfg.paused) throw new Error("Platform is paused");
  const signer = await getSigner(parsed);
  const authToken = await getAuthToken(signer);
  const positions = await getUserPositions(signer.address, "active", authToken);
  log("INFO", `Active positions found: ${positions.length}`);

  let sold = 0;
  let quoted = 0;
  let skipped = 0;
  let failed = 0;
  for (const [idx, position] of positions.entries()) {
    const index = idx + 1;
    const label = positionLabel(position, index);
    try {
      if (!ADDRESS_RE.test(position.market || "")) {
        log("WARNING", `${label} skipped: bad market address`);
        skipped += 1;
        continue;
      }
      const outcome = Number(position.outcomeIndex);
      if (!Number.isInteger(outcome) || outcome < 0) {
        log("WARNING", `${label} skipped: bad outcome index`);
        skipped += 1;
        continue;
      }
      const rawAmount = positionRawShares(position);
      if (rawAmount.lte(0)) {
        log("WARNING", `${label} skipped: zero API shares`);
        skipped += 1;
        continue;
      }
      log("INFO", label);
      const result = await sellOutcomeShares(
        parsed,
        sysCfg,
        signer,
        ethers.utils.getAddress(position.market),
        outcome,
        rawAmount,
        label
      );
      if (result === "sold") sold += 1;
      else if (result === "quoted") quoted += 1;
      else if (result === "skipped") skipped += 1;
      else failed += 1;
    } catch (error) {
      failed += 1;
      log("ERROR", `${label} sell failed: ${error.message || error}`);
    }
  }

  log("INFO", `Sell-all summary: sold=${sold}, quoted=${quoted}, skipped=${skipped}, failed=${failed}`);
}

async function redeemMarket(parsed, signerOrProvider, marketAddress, label) {
  const provider = signerOrProvider.provider || signerOrProvider;
  await assertContractCode(provider, marketAddress);
  const market = getMarketContract(marketAddress, signerOrProvider);
  const status = Number(await market.getStatus());
  if (status !== 5 && status !== 8) {
    log("WARNING", `${label} skipped: market is not redeemable, status=${statusName(status)}`);
    return "skipped";
  }
  const perShare = await market.getRedeemableAmountPerShare();
  log("INFO", `${label}`);
  log("INFO", `Redeemable amount per share: ${perShare.toString()}`);

  if (!parsed.send) {
    log("INFO", "Dry-run only. Add --send to submit.");
    return "quoted";
  }

  const tx = await market.redeem();
  log("INFO", `Redeem tx sent: ${tx.hash}`);
  const receipt = await tx.wait();
  log("INFO", `Redeem receipt status: ${receipt.status}`);
  return receipt.status === 1 ? "claimed" : "failed";
}

async function doRedeem(parsed) {
  const marketAddress = requireAddress(parsed.market, "market");
  const signerOrProvider = parsed.send ? await getSigner(parsed) : await getCheckedProvider(parsed);
  await redeemMarket(parsed, signerOrProvider, marketAddress, `Manual claim ${marketAddress}`);
}

async function getClosedPositionsForRedeem(walletAddress, authToken) {
  const all = [];
  for (const status of ["closed", "resolved"]) {
    try {
      const items = await getUserPositions(walletAddress, status, authToken);
      all.push(...items);
    } catch (error) {
      log("WARNING", `Positions status=${status} failed: ${error.message || error}`);
    }
  }
  return all;
}

async function doRedeemAll(parsed) {
  const signer = await getSigner(parsed);
  const authToken = await getAuthToken(signer);
  const positions = await getClosedPositionsForRedeem(signer.address, authToken);
  const byMarket = new Map();
  for (const position of positions) {
    if (!ADDRESS_RE.test(position.market || "")) continue;
    const address = ethers.utils.getAddress(position.market);
    if (!byMarket.has(address)) byMarket.set(address, position);
  }
  log("INFO", `Claimable/closed markets found: ${byMarket.size}`);

  let claimed = 0;
  let quoted = 0;
  let skipped = 0;
  let failed = 0;
  let index = 0;
  for (const [marketAddress, position] of byMarket.entries()) {
    index += 1;
    const label = `[claim ${index}] ${marketAddress} | ${position.marketTitle || position.title || "untitled"}`;
    try {
      const result = await redeemMarket(parsed, signer, marketAddress, label);
      if (result === "claimed") claimed += 1;
      else if (result === "quoted") quoted += 1;
      else if (result === "skipped") skipped += 1;
      else failed += 1;
    } catch (error) {
      failed += 1;
      log("ERROR", `${label} failed: ${error.message || error}`);
    }
  }

  log("INFO", `Claim trades summary: claimed=${claimed}, quoted=${quoted}, skipped=${skipped}, failed=${failed}`);
}

async function main() {
  const parsed = parseArgs();
  ensureCommand(parsed, ["system", "list-standard", "list-quick", "show", "buy", "random-buy", "tasks", "claim-quests", "sell", "sell-all", "redeem", "redeem-all"]);
  log("INFO", `API: ${API_BASE}`);

  if (parsed.command === "system") await showSystem(parsed);
  if (parsed.command === "list-standard") await listStandard(parsed);
  if (parsed.command === "list-quick") await listQuick(parsed);
  if (parsed.command === "show") await showMarket(parsed);
  if (parsed.command === "buy") await doBuy(parsed);
  if (parsed.command === "random-buy") await doRandomBuy(parsed);
  if (parsed.command === "tasks") await doRewardTasks(parsed);
  if (parsed.command === "claim-quests") await doClaimRewardQuests(parsed);
  if (parsed.command === "sell") await doSell(parsed);
  if (parsed.command === "sell-all") await doSellAll(parsed);
  if (parsed.command === "redeem") await doRedeem(parsed);
  if (parsed.command === "redeem-all") await doRedeemAll(parsed);

  log("INFO", `Log saved to: ${LOG_FILE}`);
}

main().catch((error) => {
  log("ERROR", error.stack || error.message);
  log("ERROR", `Log saved to: ${LOG_FILE}`);
  process.exitCode = 1;
});
