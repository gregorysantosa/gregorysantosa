"""Errors raised by config loading, market calls, and the purchase ledger."""


class ConfigError(ValueError):
    """The watchlist file is missing a required limit or has an invalid value."""


class MoneyParseError(ValueError):
    """A Steam price or volume string could not be read."""


class SteamError(RuntimeError):
    """The Steam market endpoint failed or returned something we will not trade on."""


class SteamAuthError(SteamError):
    """Live mode is missing the user's own Steam session cookies."""


class SteamRateLimitError(SteamError):
    """Steam answered 429 and the retry budget for this read was used up."""


class LedgerError(ValueError):
    """The purchase ledger is corrupt. Refusing to continue avoids a double spend."""
