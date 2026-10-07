from __future__ import annotations

import re


def broker_display_name(broker_text: str | None, account_number: str | None) -> str:
    """First letters of the broker name, ending with the last four account digits.

    A short hyphenated code such as Funded-XX is kept whole, so login 1234
    becomes Funded-XX1234. A longer name such as FundedNext Ltd becomes Funded-1234.
    """
    raw = str(broker_text or "").strip()
    compact = re.sub(r"\s+", "", raw)
    digits = "".join(char for char in str(account_number or "") if char.isdigit())
    last4 = digits[-4:] if len(digits) >= 4 else digits.rjust(4, "0")
    if compact and len(compact) <= 9 and "-" in compact:
        return f"{compact}{last4}"
    letters = "".join(char for char in raw if char.isalpha())
    prefix = letters[:6] or "Broker"
    return f"{prefix}-{last4}"
