const fs = require("fs");
const path = require("path");

const { ethers } = require("ethers");
const {
  ChildToParentMessageStatus,
  getArbitrumNetworkInformationFromRollup,
  registerCustomArbitrumNetwork,
} = require("@arbitrum/sdk");
const { ChildTransactionReceipt } = require("@arbitrum/sdk/dist/lib/message/ChildTransaction");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const KEYS_FILE = path.join(PROJECT_ROOT, "keys.txt");
const LOGS_DIR = path.join(PROJECT_ROOT, "logs");
fs.mkdirSync(LOGS_DIR, { recursive: true });
const LOG_FILE = path.join(
  LOGS_DIR,
  `liteforge_claim_${new Date().toISOString().replace(/[-:]/g, "").slice(0, 15).replace("T", "_")}.log`
);

const LITEFORGE_RPC = "https://liteforge.rpc.caldera.xyz/http";
const LITEFORGE_CHAIN_ID = 4441;
const SEPOLIA_CHAIN_ID = 11155111;
const LITEFORGE_ROLLUP = "0xD8c594652B205fa4c8047608FAc3ab102B6e968d";
const LITEFORGE_EXPLORER_API =
  process.env.LITEFORGE_EXPLORER_API || "https://liteforge.explorer.caldera.xyz/api";
const ARBSYS = "0x0000000000000000000000000000000000000064";
const WITHDRAW_ETH_SELECTOR = "0x25e16063";

const SEPOLIA_RPCS = [
  process.env.SEPOLIA_RPC,
  "https://ethereum-sepolia-rpc.publicnode.com",
  "https://rpc.sepolia.org",
  "https://sepolia.drpc.org",
].filter(Boolean);

const TX_RE = /^0x[0-9a-fA-F]{64}$/;

function timestamp() {
  return new Date().toTimeString().slice(0, 8);
}

function log(level, message) {
  const line = `${timestamp()}  ${level.padEnd(7)}  ${message}`;
  console.log(line);
  fs.appendFileSync(LOG_FILE, `${line}\n`, "utf8");
}

function readKeys() {
  if (!fs.existsSync(KEYS_FILE)) {
    throw new Error("keys.txt not found");
  }
  const keys = fs
    .readFileSync(KEYS_FILE, "utf8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => (line.startsWith("0x") ? line : `0x${line}`));
  if (keys.length === 0) {
    throw new Error("keys.txt is empty");
  }
  return keys;
}

function readSelectedWallet() {
  const keys = readKeys();
  const rawIndex = (process.env.KEY_INDEX || "1").trim();
  const index = Number.parseInt(rawIndex, 10);
  if (!Number.isInteger(index) || index < 1 || index > keys.length) {
    throw new Error(`Invalid KEY_INDEX=${rawIndex} for ${keys.length} keys`);
  }
  return new ethers.Wallet(keys[index - 1]);
}

function parseArgs() {
  const args = process.argv.slice(2);
  const parsed = { send: false, txs: [], all: false };
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === "--send") {
      parsed.send = true;
    } else if (arg === "--all") {
      parsed.all = true;
    } else if (arg === "--tx") {
      const value = args[i + 1];
      i += 1;
      if (!value || !TX_RE.test(value)) {
        throw new Error("--tx expects a transaction hash");
      }
      parsed.txs.push(value);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return parsed;
}

async function firstWorkingProvider(rpcs, chainId, label) {
  let lastError;
  for (const rpc of rpcs) {
    try {
      const provider = new ethers.providers.JsonRpcProvider(rpc);
      const network = await provider.getNetwork();
      if (network.chainId !== chainId) {
        throw new Error(`wrong chain id ${network.chainId}`);
      }
      log("INFO", `${label} RPC: ${rpc}`);
      return provider;
    } catch (error) {
      lastError = error;
      log("WARNING", `${label} RPC failed ${rpc}: ${error.message}`);
    }
  }
  throw new Error(`Cannot connect to ${label} RPC: ${lastError ? lastError.message : "no RPC"}`);
}

async function registerLiteForge(parentProvider) {
  const info = await getArbitrumNetworkInformationFromRollup(LITEFORGE_ROLLUP, parentProvider);
  registerCustomArbitrumNetwork({
    name: "LiteForge",
    chainId: LITEFORGE_CHAIN_ID,
    parentChainId: SEPOLIA_CHAIN_ID,
    isCustom: true,
    isTestnet: true,
    confirmPeriodBlocks: info.confirmPeriodBlocks,
    ethBridge: info.ethBridge,
    nativeToken: info.nativeToken,
  });
  log("INFO", `Outbox: ${info.ethBridge.outbox}`);
  log("INFO", `Confirm period blocks: ${info.confirmPeriodBlocks}`);
}

function findBridgeTxsForWallet(walletAddress) {
  if (!fs.existsSync(LOGS_DIR)) {
    return [];
  }
  const files = fs
    .readdirSync(LOGS_DIR)
    .filter((name) => /^liteforge_bridge_\d+_\d+\.log$/i.test(name))
    .sort();
  const walletLower = walletAddress.toLowerCase();
  const txs = [];
  let currentWallet = null;

  for (const file of files) {
    const fullPath = path.join(LOGS_DIR, file);
    const lines = fs.readFileSync(fullPath, "utf8").split(/\r?\n/);
    for (const line of lines) {
      const walletMatch = line.match(/Wallet:\s+(0x[0-9a-fA-F]{40})/);
      if (walletMatch) {
        currentWallet = walletMatch[1].toLowerCase();
        continue;
      }
      const txMatch = line.match(/Bridge withdrawal initiated:\s+(0x[0-9a-fA-F]{64})/);
      if (txMatch && currentWallet === walletLower) {
        txs.push({ txHash: txMatch[1], sourceLog: file });
      }
    }
  }

  const seen = new Set();
  return txs.filter((item) => {
    const key = item.txHash.toLowerCase();
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

async function fetchJson(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timeout);
  }
}

async function findExplorerBridgeTxsForWallet(walletAddress) {
  const walletLower = walletAddress.toLowerCase();
  const out = [];

  for (let page = 1; page <= 10; page += 1) {
    const url =
      `${LITEFORGE_EXPLORER_API}?module=account&action=txlist` +
      `&address=${walletAddress}&page=${page}&offset=100&sort=desc`;
    let body;
    try {
      body = await fetchJson(url);
    } catch (error) {
      log("WARNING", `Explorer tx scan failed page ${page}: ${error.message}`);
      break;
    }

    const rows = Array.isArray(body.result) ? body.result : [];
    if (rows.length === 0) {
      break;
    }

    for (const tx of rows) {
      const from = String(tx.from || "").toLowerCase();
      const to = String(tx.to || "").toLowerCase();
      const input = String(tx.input || "").toLowerCase();
      const ok = tx.txreceipt_status != null ? String(tx.txreceipt_status) === "1" : String(tx.isError || "0") !== "1";
      if (
        from === walletLower &&
        to === ARBSYS &&
        input.startsWith(WITHDRAW_ETH_SELECTOR) &&
        ok
      ) {
        out.push({
          txHash: tx.hash,
          sourceLog: `LiteForge explorer page ${page}`,
        });
      }
    }
  }

  return out;
}

function dedupeTxs(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = item.txHash.toLowerCase();
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function statusName(status) {
  if (status === ChildToParentMessageStatus.UNCONFIRMED) return "UNCONFIRMED";
  if (status === ChildToParentMessageStatus.CONFIRMED) return "CONFIRMED";
  if (status === ChildToParentMessageStatus.EXECUTED) return "EXECUTED";
  return `UNKNOWN(${status})`;
}

async function processBridgeTx({ txHash, sourceLog }, wallet, childProvider, parentSigner, send) {
  log("INFO", `Bridge tx: ${txHash}`);
  if (sourceLog) {
    log("INFO", `Source log: ${sourceLog}`);
  }

  const receipt = await childProvider.getTransactionReceipt(txHash);
  if (!receipt) {
    log("WARNING", "LiteForge receipt not found, skipped");
    return { claimed: false, ready: false, skipped: true };
  }
  if (receipt.status !== 1) {
    log("WARNING", `LiteForge receipt status is ${receipt.status}, skipped`);
    return { claimed: false, ready: false, skipped: true };
  }

  const childReceipt = new ChildTransactionReceipt(receipt);
  const messages = await childReceipt.getChildToParentMessages(parentSigner);
  if (messages.length === 0) {
    log("WARNING", "No child-to-parent message found, skipped");
    return { claimed: false, ready: false, skipped: true };
  }

  let claimedAny = false;
  let readyAny = false;
  for (const message of messages) {
    const status = await message.status(childProvider);
    log("INFO", `Claim status: ${statusName(status)}`);
    if (status === ChildToParentMessageStatus.EXECUTED) {
      log("INFO", "Already claimed, skipped");
      continue;
    }
    if (status === ChildToParentMessageStatus.UNCONFIRMED) {
      const firstExecutable = await message.getFirstExecutableBlock(childProvider).catch(() => null);
      if (firstExecutable) {
        log("INFO", `Not ready yet. First executable Sepolia block estimate: ${firstExecutable.toString()}`);
      } else {
        log("INFO", "Not ready yet");
      }
      continue;
    }
    if (status !== ChildToParentMessageStatus.CONFIRMED) {
      log("WARNING", "Unknown status, skipped");
      continue;
    }

    readyAny = true;
    if (!send) {
      log("INFO", "Ready to claim. Add --send to execute.");
      continue;
    }

    const balance = await parentSigner.provider.getBalance(wallet.address);
    log("INFO", `Sepolia balance: ${ethers.utils.formatEther(balance)} ETH`);
    const claimTx = await message.execute(childProvider);
    log("INFO", `Claim tx sent: ${claimTx.hash}`);
    const claimReceipt = await claimTx.wait();
    log("INFO", `Claim receipt status: ${claimReceipt.status}`);
    log("INFO", `Claim block: ${claimReceipt.blockNumber}`);
    log("INFO", `Claim gas used: ${claimReceipt.gasUsed.toString()}`);
    log("INFO", `Claim explorer: https://sepolia.etherscan.io/tx/${claimTx.hash}`);
    if (claimReceipt.status !== 1) {
      throw new Error(`Claim transaction reverted: ${claimTx.hash}`);
    }
    claimedAny = true;
  }

  return { claimed: claimedAny, ready: readyAny, skipped: false };
}

async function main() {
  const args = parseArgs();
  const wallet = readSelectedWallet();

  log("INFO", `Wallet: ${wallet.address}`);
  log("INFO", `Mode: ${args.send ? "SEND" : "STATUS ONLY"}`);

  const childProvider = await firstWorkingProvider([LITEFORGE_RPC], LITEFORGE_CHAIN_ID, "LiteForge");
  const parentProvider = await firstWorkingProvider(SEPOLIA_RPCS, SEPOLIA_CHAIN_ID, "Sepolia");
  await registerLiteForge(parentProvider);

  const parentSigner = wallet.connect(parentProvider);
  const localTxs = args.txs.length
    ? args.txs.map((txHash) => ({ txHash, sourceLog: "manual --tx" }))
    : findBridgeTxsForWallet(wallet.address);
  const explorerTxs = args.txs.length ? [] : await findExplorerBridgeTxsForWallet(wallet.address);
  const txs = dedupeTxs([...localTxs, ...explorerTxs]);

  if (txs.length === 0) {
    log("WARNING", "No LiteForge bridge withdrawals found for this wallet in logs or explorer history");
    return 2;
  }

  log("INFO", `Found bridge withdrawals: ${txs.length}`);
  let claimedCount = 0;
  let readyCount = 0;
  let checkedCount = 0;

  for (const item of txs) {
    checkedCount += 1;
    const result = await processBridgeTx(item, wallet, childProvider, parentSigner, args.send);
    if (result.claimed) claimedCount += 1;
    if (result.ready) readyCount += 1;
    if (!args.all && result.claimed) {
      break;
    }
  }

  log("INFO", `Checked: ${checkedCount}`);
  log("INFO", `Ready: ${readyCount}`);
  log("INFO", `Claimed: ${claimedCount}`);
  log("INFO", `Log saved to: ${LOG_FILE}`);
  if (args.send && claimedCount === 0) {
    return 2;
  }
  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((error) => {
    log("ERROR", `Fatal error: ${error.stack || error.message}`);
    process.exit(1);
  });
