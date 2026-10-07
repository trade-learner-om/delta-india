from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SETTLEMENT_ASSETS = ("USD", "USDT", "INR")


@dataclass
class WalletSummary:
    asset_symbol: str
    balance: float
    available_balance: float
    net_equity: float | None
    robo_trading_equity: float | None = None


def parse_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_number_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def wallet_row_available(item: dict[str, Any]) -> float:
    """Per-asset margin for trading, including FNO/robo wallet fields."""
    standard = parse_number(item.get("available_balance"))
    robo = parse_number(item.get("available_balance_for_robo"))
    return max(standard, robo)


def wallet_row_balance(item: dict[str, Any]) -> float:
    return parse_number(item.get("balance"))


def meta_account_equity(meta: dict[str, Any] | None) -> float | None:
    """Account-level equity from wallet payload meta (FNO / cross-margin)."""
    if not meta:
        return None
    values = [
        parse_number_or_none(meta.get("net_equity")),
        parse_number_or_none(meta.get("robo_trading_equity")),
    ]
    positives = [value for value in values if value is not None and value > 0]
    return max(positives) if positives else None


def resolve_wallet_margin(
    wallets: dict[str, tuple[float, float]],
    net_equity: float | None = None,
    robo_trading_equity: float | None = None,
) -> WalletSummary:
    """Resolve available margin from Delta wallet rows and meta."""
    best_available = 0.0
    best_balance = 0.0
    best_asset = "USD"

    for symbol, (item_available, item_balance) in wallets.items():
        if item_available > best_available:
            best_available = item_available
            best_balance = item_balance
            best_asset = symbol

    account_equity_values = [
        value
        for value in (net_equity, robo_trading_equity)
        if value is not None and value > 0
    ]
    account_equity = max(account_equity_values) if account_equity_values else None

    available = best_available
    balance = best_balance
    asset = best_asset or "USD"

    if account_equity is not None and account_equity > available:
        available = account_equity
        if balance <= 0:
            balance = account_equity
        settlement_asset = next((symbol for symbol in SETTLEMENT_ASSETS if symbol in wallets), None)
        asset = settlement_asset or best_asset or "USD"

    return WalletSummary(asset, balance, available, net_equity, robo_trading_equity)


def map_wallet_payload(node: dict) -> WalletSummary:
    """Map Delta GET /v2/wallet/balances payload."""
    meta = node.get("meta") or {}
    net_equity = parse_number_or_none(meta.get("net_equity"))
    robo_trading_equity = parse_number_or_none(meta.get("robo_trading_equity"))
    wallets: dict[str, tuple[float, float]] = {}
    for item in node.get("result", []):
        symbol = str(item.get("asset_symbol") or "").strip().upper()
        if not symbol:
            continue
        wallets[symbol] = (wallet_row_available(item), wallet_row_balance(item))
    return resolve_wallet_margin(wallets, net_equity, robo_trading_equity)


@dataclass
class WalletMarginTracker:
    """Accumulates per-asset margin updates from the private WS ``margins`` channel."""

    wallets: dict[str, tuple[float, float]]
    net_equity: float | None = None
    robo_trading_equity: float | None = None

    @classmethod
    def empty(cls) -> WalletMarginTracker:
        return cls(wallets={})

    def has_margin_data(self) -> bool:
        if meta_account_equity(
            {
                "net_equity": self.net_equity,
                "robo_trading_equity": self.robo_trading_equity,
            }
        ):
            return True
        return any(available > 0 for available, _balance in self.wallets.values())

    def apply_margin_message(self, message: dict[str, Any]) -> None:
        symbol = str(message.get("asset_symbol") or "").strip().upper()
        if symbol:
            self.wallets[symbol] = (wallet_row_available(message), wallet_row_balance(message))
        robo_equity = parse_number_or_none(message.get("robo_trading_equity"))
        if robo_equity is not None and robo_equity > 0:
            self.robo_trading_equity = robo_equity

    def summary(self) -> WalletSummary:
        return resolve_wallet_margin(self.wallets, self.net_equity, self.robo_trading_equity)

    def load_wallet_payload(self, node: dict) -> None:
        meta = node.get("meta") or {}
        self.wallets = {}
        for item in node.get("result", []):
            symbol = str(item.get("asset_symbol") or "").strip().upper()
            if not symbol:
                continue
            self.wallets[symbol] = (wallet_row_available(item), wallet_row_balance(item))
        self.net_equity = parse_number_or_none(meta.get("net_equity"))
        self.robo_trading_equity = parse_number_or_none(meta.get("robo_trading_equity"))
