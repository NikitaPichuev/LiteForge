const fs = require("fs");
const path = require("path");

const { ethers } = require("ethers");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const KEYS_FILE = path.join(PROJECT_ROOT, "keys.txt");
const LOGS_DIR = path.join(PROJECT_ROOT, "logs");
fs.mkdirSync(LOGS_DIR, { recursive: true });

const LOG_FILE = path.join(
  LOGS_DIR,
  `liteforge_native_balance_${new Date().toISOString().replace(/[-:]/g, "").slice(0, 15).replace("T", "_")}.log`
);

const DEFAULT_RPC = "https://liteforge.rpc.caldera.xyz/http";
const RPC_URL = process.env.LITEFORGE_RPC_URL || process.env.MIDAS_RPC_URL || process.env.EVM_RPC_URL || DEFAULT_RPC;

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
LiteForge native balance checker

Commands:
  node app\\liteforge_native_balance.js --wallet-index 1
  node app\\liteforge_native_balance.js --all
  node app\\liteforge_native_balance.js --all --min 0.002
  node app\\liteforge_native_balance.js --all --retries 5 --delay-ms 700

Env:
  LITEFORGE_RPC_URL, MIDAS_RPC_URL, or EVM_RPC_URL can override the RPC.
`);
}

function parseArgs() {
  const parsed = {
    all: false,
    walletIndex: Number.parseInt(process.env.KEY_INDEX || "1", 10),
    min: null,
    retries: 5,
    delayMs: 700,
  };
  const args = process.argv.slice(2);
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === "--all") parsed.all = true;
    else if (arg === "--wallet-index") parsed.walletIndex = Number.parseInt(args[++i], 10);
    else if (arg === "--min") parsed.min = String(args[++i] || "");
    else if (arg === "--retries") parsed.retries = Number.parseInt(args[++i], 10);
    else if (arg === "--delay-ms") parsed.delayMs = Number.parseInt(args[++i], 10);
    else if (arg === "--help" || arg === "-h") {
      usage();
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!Number.isInteger(parsed.retries) || parsed.retries < 1) throw new Error("--retries must be >= 1");
  if (!Number.isInteger(parsed.delayMs) || parsed.delayMs < 0) throw new Error("--delay-ms must be >= 0");
  return parsed;
}

function readKeys() {
  if (!fs.existsSync(KEYS_FILE)) throw new Error(`keys.txt not found: ${KEYS_FILE}`);
  const keys = fs
    .readFileSync(KEYS_FILE, "utf8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => (line.startsWith("0x") ? line : `0x${line}`));
  if (keys.length === 0) throw new Error("keys.txt is empty");
  return keys;
}

function selectWallets(parsed) {
  const keys = readKeys();
  if (parsed.all) return keys.map((privateKey, index) => ({ privateKey, index: index + 1 }));
  if (!Number.isInteger(parsed.walletIndex) || parsed.walletIndex < 1 || parsed.walletIndex > keys.length) {
    throw new Error(`Invalid wallet index ${parsed.walletIndex}; keys.txt has ${keys.length} keys`);
  }
  return [{ privateKey: keys[parsed.walletIndex - 1], index: parsed.walletIndex }];
}

function formatNative(balance) {
  return ethers.utils.formatEther(balance);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function compactError(error) {
  if (!error) return "unknown error";
  const code = error.code || error.serverError?.code;
  const reason = error.reason || error.message || String(error);
  return code ? `${code}: ${reason}` : reason;
}

async function getBalanceWithRetry(provider, address, retries, delayMs) {
  let lastError;
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      return await provider.getBalance(address);
    } catch (error) {
      lastError = error;
      if (attempt < retries) {
        log("WARNING", `${address} balance read failed, retry ${attempt}/${retries}: ${compactError(error)}`);
        await sleep(delayMs * attempt);
      }
    }
  }
  throw lastError;
}

async function main() {
  const parsed = parseArgs();
  const selected = selectWallets(parsed);
  const provider = new ethers.providers.JsonRpcProvider(RPC_URL);
  const network = await provider.getNetwork();
  const minWei = parsed.min == null || parsed.min === "" ? null : ethers.utils.parseEther(parsed.min);

  log("INFO", `RPC: ${RPC_URL}`);
  log("INFO", `Chain id: ${network.chainId}`);
  log("INFO", `Wallets selected: ${selected.length}`);
  if (minWei) log("INFO", `Minimum balance: ${parsed.min} zkLTC (${minWei.toString()} wei)`);

  let total = ethers.BigNumber.from(0);
  let belowMin = 0;
  let errorCount = 0;

  for (const item of selected) {
    const wallet = new ethers.Wallet(item.privateKey);
    const address = ethers.utils.getAddress(wallet.address);
    try {
      const balance = await getBalanceWithRetry(provider, address, parsed.retries, parsed.delayMs);
      total = total.add(balance);
      const mark = minWei && balance.lt(minWei) ? "LOW" : "OK";
      if (mark === "LOW") belowMin += 1;
      log("INFO", `[wallet ${item.index}] ${address} balance=${formatNative(balance)} zkLTC | wei=${balance.toString()} | ${mark}`);
    } catch (error) {
      errorCount += 1;
      log("ERROR", `[wallet ${item.index}] ${address} balance read failed after ${parsed.retries} attempts: ${compactError(error)}`);
    }
    if (parsed.delayMs > 0) await sleep(parsed.delayMs);
  }

  log("INFO", `Total native balance: ${formatNative(total)} zkLTC | wei=${total.toString()}`);
  if (minWei) log("INFO", `Below minimum: ${belowMin}/${selected.length}`);
  if (errorCount > 0) log("WARNING", `Balance read errors: ${errorCount}/${selected.length}`);
  log("INFO", `Log saved to: ${LOG_FILE}`);
}

main().catch((error) => {
  log("ERROR", error && error.stack ? error.stack : String(error));
  log("INFO", `Log saved to: ${LOG_FILE}`);
  process.exitCode = 1;
});
