"""
Pre-run checks for the LitVM bot.

This module never prints private key or proxy values.
It only reports whether required files and config values are present.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
from dataclasses import dataclass
from typing import Iterable

import config


BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
KEYS_FILE = BASE_DIR / "keys.txt"
PROXIES_FILE = BASE_DIR / "proxies.txt"
ZERO_ADDRESS = "0x" + "0" * 40
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


@dataclass
class CheckReport:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def _read_non_comment_lines(path: pathlib.Path) -> list[str]:
    if not path.exists():
        return []
    lines = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def _is_zero_address(value: object) -> bool:
    return isinstance(value, str) and value.lower() == ZERO_ADDRESS


def _check_address(name: str, value: object, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{name}: empty or not a string")
        return
    if _is_zero_address(value):
        errors.append(f"{name}: zero address, fill it in config.py")
        return
    if not ADDRESS_RE.match(value):
        errors.append(f"{name}: invalid address format: {value}")


def _check_optional_address(name: str, value: object, warnings: list[str]) -> None:
    if value in (None, "", ZERO_ADDRESS):
        return
    if not isinstance(value, str) or not ADDRESS_RE.match(value):
        warnings.append(f"{name}: optional address has invalid format: {value}")


def _require_packages(names: Iterable[str], errors: list[str]) -> None:
    for package in names:
        if importlib.util.find_spec(package) is None:
            errors.append(
                f"Python package is missing: {package}. "
                f"Run menu.bat -> option 1, or `python -m pip install -r requirements.txt`."
            )


def run_checks(strict_config: bool = True) -> CheckReport:
    errors: list[str] = []
    warnings: list[str] = []

    _require_packages(["web3", "eth_account", "requests"], errors)

    key_lines = _read_non_comment_lines(KEYS_FILE)
    if not key_lines:
        errors.append("keys.txt is missing or empty. Put one private key there, or set PRIVATE_KEY.")
    elif len(key_lines[0].replace("0x", "", 1)) < 64:
        warnings.append("keys.txt first key looks shorter than a normal private key.")

    proxy_lines = _read_non_comment_lines(PROXIES_FILE)
    if len(proxy_lines) > 1:
        warnings.append("proxies.txt has multiple entries; only the first one will be used.")

    if getattr(config, "CHAIN_ID", None) != 4441:
        warnings.append(f"CHAIN_ID is {getattr(config, 'CHAIN_ID', None)}, expected 4441 for LitVM LiteForge.")

    _check_address("USDC", getattr(config, "USDC", None), errors)

    if getattr(config, "ENABLE_LITESWAP", False):
        _check_address("LITESWAP_ROUTER", getattr(config, "LITESWAP_ROUTER", None), errors)
        _check_address("WZKLTC", getattr(config, "WZKLTC", None), errors)
        _check_optional_address("LITESWAP_FACTORY", getattr(config, "LITESWAP_FACTORY", None), warnings)
        _check_optional_address("LITESWAP_STAKING", getattr(config, "LITESWAP_STAKING", None), warnings)

    if getattr(config, "ENABLE_OMNI", False):
        _check_address("OMNI_ROUTER", getattr(config, "OMNI_ROUTER", None), errors)
        _check_address("WZKLTC", getattr(config, "WZKLTC", None), errors)
        target = getattr(config, "OMNI_TARGET_TOKEN", ZERO_ADDRESS)
        if _is_zero_address(target):
            errors.append("OMNI_TARGET_TOKEN: zero address, fill it in config.py or disable ENABLE_OMNI.")
        else:
            _check_address("OMNI_TARGET_TOKEN", target, errors)

    if getattr(config, "ENABLE_AYNI", False):
        _check_address("AYNI_POOL", getattr(config, "AYNI_POOL", None), errors)
        _check_address("WZKLTC", getattr(config, "WZKLTC", None), errors)

    if getattr(config, "ENABLE_LESTER", False):
        _check_address("LESTER_FACTORY", getattr(config, "LESTER_FACTORY", None), errors)

    if getattr(config, "ENABLE_OMNI_CREATE", False):
        _check_address("OMNI_FACTORY", getattr(config, "OMNI_FACTORY", None), errors)
        if not getattr(config, "OMNI_METADATA_URI", ""):
            warnings.append("OMNI_METADATA_URI is empty; Omni coin creation may fail validation.")

    if not strict_config:
        warnings.extend(errors)
        errors = []

    errors = list(dict.fromkeys(errors))
    warnings = list(dict.fromkeys(warnings))
    return CheckReport(errors=errors, warnings=warnings)


def print_report(report: CheckReport) -> None:
    if report.ok:
        print("[OK] Pre-run checks passed.")
    else:
        print("[ERROR] Pre-run checks failed.")

    if report.errors:
        print("\nErrors:")
        for item in report.errors:
            print(f"  - {item}")

    if report.warnings:
        print("\nWarnings:")
        for item in report.warnings:
            print(f"  - {item}")
