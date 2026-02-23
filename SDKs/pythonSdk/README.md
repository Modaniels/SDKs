# Modexia Python SDK

Lightweight Python client for interacting with the Modexia AgentPay API.

Features
- Simple programmatic access to agent wallets and payments
- Reliable retry/backoff for HTTP calls
- Small surface area: `ModexiaClient` with `transfer` + `retrieve_balance` (or `get_balance`) helpers

Installation

```bash
# install locally (editable)
pip install -e packages/SDKs/pythonSdk
```

Quick start

```python
from modexia import ModexiaClient

client = ModexiaClient(api_key="mx_test_...")

# you can also override the base url, or skip network validation
# client = ModexiaClient(api_key="mx_test_...", base_url="http://custom.url", validate=False)
# It will also respect the MODEXIA_BASE_URL environment variable

# read balance
print(client.retrieve_balance())
# print(client.get_balance()) # alias

# make a transfer (wait=True polls for on-chain confirmation)
receipt = client.transfer(recipient="0xabc...", amount=5.0, wait=True)
print(receipt)
```

API (short)
- ModexiaClient(api_key: str, timeout: int = 15, base_url: Optional[str] = None, validate: bool = True)
	- retrieve_balance() -> str
	- get_balance() -> str (alias for retrieve_balance)
	- transfer(recipient: str, amount: float, idempotency_key: Optional[str] = None, wait: bool = True) -> dict
	- smart_fetch(url, ...) -> requests.Response

Errors / Exceptions
- ModexiaAuthError — authentication problems
- ModexiaPaymentError — payment/server errors
- ModexiaNetworkError — network/connection failures

Testing

Run the unit tests with pytest from the repository root:

```bash
pytest -q packages/SDKs/pythonSdk
```

Contributing

Open a PR against the `develop` branch. Keep API names stable — this package uses
`ModexiaClient` and `transfer(...)` as the canonical surface.

Install (PyPI)

```bash
pip install modexiaagentpay
```

If you prefer to try the local copy while iterating:

```bash
pip install -e packages/SDKs/pythonSdk
```
