"""
Web3 client:
  - reads private key from keys.txt (or PRIVATE_KEY env var as fallback)
  - reads proxy from proxies.txt (or config.PROXY as fallback)
  - safe nonce tracking, tx signing/sending with EIP-1559 gas
"""
import os
import time
import random
import logging
import pathlib
from typing import Optional

import requests
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account

import config
from key_utils import get_active_key_index, read_key_lines

log = logging.getLogger("client")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
KEYS_FILE    = PROJECT_ROOT / "keys.txt"
PROXIES_FILE = PROJECT_ROOT / "proxies.txt"


def _read_lines(path: pathlib.Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def _normalize_proxy(raw: str) -> str:
    """Accept several formats, return a requests-compatible URL.

    Supported:
      http://user:pass@host:port
      socks5://user:pass@host:port
      user:pass@host:port            -> http://user:pass@host:port
      host:port:user:pass            -> http://user:pass@host:port
      host:port                      -> http://host:port
    """
    raw = raw.strip()
    if "://" in raw:
        return raw
    # user:pass@host:port  (no scheme)
    if "@" in raw:
        return f"http://{raw}"
    parts = raw.split(":")
    if len(parts) == 2:                       # host:port
        host, port = parts
        return f"http://{host}:{port}"
    if len(parts) == 4:                       # host:port:user:pass
        host, port, user, pwd = parts
        return f"http://{user}:{pwd}@{host}:{port}"
    raise ValueError(f"unrecognized proxy format: {raw}")


def load_proxy() -> Optional[str]:
    lines = _read_lines(PROXIES_FILE)
    if lines:
        p = _normalize_proxy(lines[0])
        log.info("Using proxy from proxies.txt: %s", _mask(p))
        return p
    if getattr(config, "PROXY", None):
        log.info("Using proxy from config.PROXY: %s", _mask(config.PROXY))
        return config.PROXY
    log.info("No proxy configured")
    return None


def _mask(proxy: str) -> str:
    """Hide password when logging."""
    try:
        if "@" in proxy:
            scheme, rest = proxy.split("://", 1)
            creds, host = rest.split("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                return f"{scheme}://{user}:***@{host}"
        return proxy
    except Exception:
        return "***"


def _make_session(proxy: Optional[str]) -> requests.Session:
    s = requests.Session()
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; LitVMBot/1.0)"})
    return s


def make_web3() -> Web3:
    proxy   = load_proxy()
    session = _make_session(proxy)
    provider = Web3.HTTPProvider(
        config.RPC_HTTP,
        session=session,
        request_kwargs={"timeout": 30},
    )
    w3 = Web3(provider)
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    if not w3.is_connected():
        raise RuntimeError(f"Cannot connect to RPC {config.RPC_HTTP} (proxy={_mask(proxy) if proxy else 'none'})")
    actual_chain = w3.eth.chain_id
    if actual_chain != config.CHAIN_ID:
        raise RuntimeError(f"Chain ID mismatch: got {actual_chain}, expected {config.CHAIN_ID}")
    log.info("Connected to %s (chain %d)", config.RPC_HTTP, actual_chain)
    return w3


def load_account() -> Account:
    # Priority: keys.txt first line → env var PRIVATE_KEY
    lines = read_key_lines(KEYS_FILE)
    pk = None
    if lines:
        key_index = get_active_key_index()
        if key_index > len(lines):
            raise RuntimeError(
                f"KEY_INDEX={key_index} is out of range for keys.txt with {len(lines)} keys."
            )
        pk = lines[key_index - 1]
        log.info("Loaded key #%d from keys.txt", key_index)
    else:
        pk = os.environ.get("PRIVATE_KEY")
        if pk:
            log.info("Loaded key from env var PRIVATE_KEY")
    if not pk:
        raise RuntimeError(
            "No private key found. Put it in keys.txt or set PRIVATE_KEY env var."
        )
    pk = pk.strip()
    if not pk.startswith("0x"):
        pk = "0x" + pk
    acct = Account.from_key(pk)
    log.info("Account: %s", acct.address)
    return acct


class Tx:
    """Stateful tx builder/sender with local nonce tracking."""

    def __init__(self, w3: Web3, account):
        self.w3 = w3
        self.account = account
        self._nonce = w3.eth.get_transaction_count(account.address, "pending")

    def _gas_price(self) -> dict:
        max_fee = int(Web3.to_wei(config.MAX_FEE_GWEI, "gwei"))
        prio    = int(Web3.to_wei(config.PRIORITY_FEE_GWEI, "gwei"))
        return {"maxFeePerGas": max_fee, "maxPriorityFeePerGas": prio}

    def send(self, tx: dict, label: str = "") -> str:
        tx.setdefault("from",     self.account.address)
        tx.setdefault("chainId",  config.CHAIN_ID)
        tx.setdefault("nonce",    self._nonce)
        tx.update(self._gas_price())
        try:
            est = self.w3.eth.estimate_gas(tx)
            tx["gas"] = int(est * config.GAS_MULTIPLIER)
        except Exception as e:
            log.warning("[%s] gas estimation failed (%s), using 500k", label, e)
            tx["gas"] = 500_000

        signed = self.account.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        h_hex = h.hex()
        log.info("[%s] sent tx %s", label, h_hex)

        rcpt = self.w3.eth.wait_for_transaction_receipt(h, timeout=180)
        status = "OK" if rcpt.status == 1 else "FAIL"
        log.info("[%s] %s  block=%d  gasUsed=%d  %s/tx/%s",
                 label, status, rcpt.blockNumber, rcpt.gasUsed,
                 config.EXPLORER, h_hex)
        if rcpt.status != 1:
            raise RuntimeError(f"tx reverted: {h_hex}")

        self._nonce += 1
        return h_hex

    def sleep_random(self):
        t = random.uniform(config.DELAY_MIN, config.DELAY_MAX)
        log.info("sleeping %.1fs", t)
        time.sleep(t)
