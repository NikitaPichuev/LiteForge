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
  `midaspredict_faucet_${new Date().toISOString().replace(/[-:]/g, "").slice(0, 15).replace("T", "_")}.log`
);

const API_BASE = process.env.MIDAS_API_BASE || "https://predict-testnet-api.midashand.xyz/api";
const ADDRESS_RE = /^0x[0-9a-fA-F]{40}$/;

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
MidasPredict faucet

Commands:
  node app\\midaspredict_faucet.js --token usdc --wallet-index 1 [--send]
  node app\\midaspredict_faucet.js --token zkltc --wallet-index 1 [--send]
  node app\\midaspredict_faucet.js --token both --all [--pause-min 4 --pause-max 10] [--send]

Notes:
  Faucet API requires auth. The script signs the Midas auth message with keys.txt.
  Without --send it only prints planned requests.
  Faucet responses are taken directly from the site API; no local cooldown is used.
`);
}

function parseArgs() {
  const parsed = {
    token: "usdc",
    walletIndex: Number.parseInt(process.env.KEY_INDEX || "1", 10),
    all: false,
    send: false,
    pauseMin: 4,
    pauseMax: 10,
  };
  const args = process.argv.slice(2);
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === "--token") parsed.token = String(args[++i] || "").toLowerCase();
    else if (arg === "--wallet-index") parsed.walletIndex = Number.parseInt(args[++i], 10);
    else if (arg === "--all") parsed.all = true;
    else if (arg === "--send") parsed.send = true;
    else if (arg === "--pause-min") parsed.pauseMin = Number.parseFloat(args[++i]);
    else if (arg === "--pause-max") parsed.pauseMax = Number.parseFloat(args[++i]);
    else if (arg === "--captcha-token") parsed.captchaToken = args[++i];
    else if (arg === "--help" || arg === "-h") {
      usage();
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!["usdc", "zkltc", "both"].includes(parsed.token)) throw new Error("--token must be usdc, zkltc, or both");
  if (!Number.isFinite(parsed.pauseMin) || !Number.isFinite(parsed.pauseMax) || parsed.pauseMin < 0 || parsed.pauseMax < parsed.pauseMin) {
    throw new Error("Invalid pause range");
  }
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

function requestJson(method, route, body, token) {
  return new Promise((resolve, reject) => {
    const url = new URL(route.startsWith("http") ? route : `${API_BASE}${route}`);
    const payload = body == null ? null : JSON.stringify(body);
    const headers = { accept: "application/json" };
    if (payload) {
      headers["content-type"] = "application/json";
      headers["content-length"] = Buffer.byteLength(payload);
    }
    if (token) headers.authorization = `Bearer ${token}`;

    const req = https.request(
      url,
      {
        method,
        headers,
      },
      (res) => {
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
      }
    );
    req.on("error", reject);
    if (payload) req.write(payload);
    req.end();
  });
}

async function getNonceMessage(address) {
  const url = `/auth/nonce?walletAddress=${encodeURIComponent(address)}`;
  const body = await requestJson("GET", url);
  if (!body || !body.success || !body.data || !body.data.message) {
    throw new Error(`Unexpected nonce response: ${JSON.stringify(body)}`);
  }
  return body.data.message;
}

async function getAuthToken(wallet, captchaToken) {
  const address = await wallet.getAddress();
  const existing = await requestJson("POST", "/auth/wallet", { walletAddress: address }).catch((error) => {
    log("WARNING", `Wallet auth check failed for ${address}: ${error.message}`);
    return null;
  });
  if (existing && existing.success && existing.data && existing.data.registered && existing.data.accessToken) {
    return existing.data.accessToken;
  }

  const message = await getNonceMessage(address);
  const signature = await wallet.signMessage(message);
  const displayName = `midas-${address.slice(-6).toLowerCase()}`;
  const registered = await requestJson("POST", "/auth/wallet/register", {
    walletAddress: address,
    signature,
    message,
    displayName,
    captchaToken,
  });
  if (!registered || !registered.success || !registered.data || !registered.data.accessToken) {
    throw new Error(`Unexpected register response: ${JSON.stringify(registered)}`);
  }
  return registered.data.accessToken;
}

async function requestFaucet(token, address, authToken) {
  const route = token === "usdc" ? "/users/faucet_usdc" : "/users/faucet_native";
  return requestJson("POST", route, { walletAddress: address }, authToken);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function randomPauseMs(min, max) {
  return Math.round((min + Math.random() * (max - min)) * 1000);
}

async function main() {
  const parsed = parseArgs();
  log("INFO", `API: ${API_BASE}`);
  const selected = selectWallets(parsed);
  const tokens = parsed.token === "both" ? ["usdc", "zkltc"] : [parsed.token];
  log("INFO", `Wallets selected: ${selected.length}`);
  log("INFO", `Tokens selected: ${tokens.join(", ")}`);

  if (!parsed.send) {
    for (const item of selected) {
      const wallet = new ethers.Wallet(item.privateKey);
      log("INFO", `[wallet ${item.index}] dry-run faucet target: ${wallet.address}`);
    }
    log("INFO", "Dry-run only. Add --send to request faucet.");
    return;
  }

  let ok = 0;
  let failed = 0;
  let skipped = 0;

  for (let i = 0; i < selected.length; i += 1) {
    const item = selected[i];
    const wallet = new ethers.Wallet(item.privateKey);
    const address = ethers.utils.getAddress(wallet.address);
    if (!ADDRESS_RE.test(address)) throw new Error(`Invalid derived address: ${address}`);
    log("INFO", `[wallet ${item.index}/${selected.length}] address: ${address}`);

    let token;
    try {
      token = await getAuthToken(wallet, parsed.captchaToken);
      log("INFO", `[wallet ${item.index}] auth OK`);
    } catch (error) {
      skipped += tokens.length;
      log("WARNING", `[wallet ${item.index}] auth failed: ${error.message}`);
      log("WARNING", `[wallet ${item.index}] skipped. If this is a new Midas account, open the site once and pass captcha/register manually.`);
      if (i < selected.length - 1) {
        const delay = randomPauseMs(parsed.pauseMin, parsed.pauseMax);
        log("INFO", `[wallet ${item.index}] pause before next wallet: ${(delay / 1000).toFixed(1)}s`);
        await sleep(delay);
      }
      continue;
    }

    for (const faucetToken of tokens) {
      try {
        const result = await requestFaucet(faucetToken, address, token);
        ok += 1;
        log("INFO", `[wallet ${item.index}] faucet ${faucetToken} response: ${JSON.stringify(result)}`);
      } catch (error) {
        failed += 1;
        log("WARNING", `[wallet ${item.index}] faucet ${faucetToken} failed: ${error.message}`);
      }
      if (tokens.length > 1) {
        const delay = randomPauseMs(parsed.pauseMin, parsed.pauseMax);
        log("INFO", `[wallet ${item.index}] pause between faucet tokens: ${(delay / 1000).toFixed(1)}s`);
        await sleep(delay);
      }
    }

    if (i < selected.length - 1) {
      const delay = randomPauseMs(parsed.pauseMin, parsed.pauseMax);
      log("INFO", `[wallet ${item.index}] pause before next wallet: ${(delay / 1000).toFixed(1)}s`);
      await sleep(delay);
    }
  }

  log("INFO", `Summary: ok=${ok}, failed=${failed}, skipped=${skipped}`);
}

main()
  .then(() => {
    log("INFO", `Log saved to: ${LOG_FILE}`);
  })
  .catch((error) => {
    log("ERROR", error.stack || error.message);
    log("ERROR", `Log saved to: ${LOG_FILE}`);
    process.exitCode = 1;
  });
