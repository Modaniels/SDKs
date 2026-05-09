---
noteId: "8d8416b04bd411f18bfe97159fe8ca5e"
tags: []

---

# Changelog

All notable changes to the Modexia Python SDK (`modexiaagentpay`) will be documented in this file.

## [0.7.0] - 2026-05-09

### 🚀 Intent-to-Pay System

A new cryptographically signed payment system that gives agents rich compliance feedback, audit trails, and policy-aware spending.

#### Added

- **`client.pay(recipient, amount, memo)`** — High-level intent-based payment. Creates a signed intent, submits it through an 11-step validation pipeline, and returns an `IntentResult` with compliance metadata (daily spend, remaining budget, balance after payment).
- **`client.create_intent(recipient, amount, memo, action, ttl_seconds)`** — Create and HMAC-SHA256 sign a payment intent token locally (no network call).
- **`client.submit_intent(intent_token)`** — Submit a signed intent token for backend validation and execution.
- **`client.get_intent(intent_id)`** — Look up the status of a previously submitted intent.
- **`client.list_intents(limit)`** — List recent payment intents for audit trail review.
- **`IntentResult` dataclass** — Rich response model with `status`, `txId`, `wallet_balance_after`, `daily_spent`, `daily_remaining`, `reason`, `code`, `suggestion`, and full `validation` pipeline results.
- **`memo` parameter** on `transfer()`, `pay()`, and `create_intent()` — Human-readable reason for each payment, stored in the audit trail and visible in the dashboard.
- **`memo` field** on `TransactionHistoryItem` — Transaction history now surfaces the memo.

#### Changed

- `transfer()` now internally routes through the same validation pipeline as `pay()`, gaining compliance enforcement with zero API changes.
- Bumped `VERSION` constant to `0.7.0` in both sync and async clients.

### 🔒 Security

- Intent tokens are HMAC-SHA256 signed using the API key as the secret.
- Backend verifies signatures using constant-time comparison (`crypto.timingSafeEqual`).
- Replay protection via nonce uniqueness enforcement.
- Intent expiry validation (default 5 minutes TTL).
- Token size limited to 10KB (DoS prevention).
- Memo truncated to 500 characters (DB bloat prevention).

---

## [0.6.1] - 2026-04-18

### Security

- Updated dependencies to resolve known vulnerabilities.
- Hardened HTTP session security warnings for non-localhost HTTP connections.

---

## [0.6.0] - 2026-04-15

### Added

- **Payment Channels (Vault):** `open_channel()`, `consume_channel()`, `settle_channel()`, `get_channel()`, `list_channels()` for high-frequency micropayments.
- **`ConsumeResponse`** and **`ChannelReceipt`** dataclasses with HMAC-signed receipts.
- **`ChannelStatus`** dataclass for channel state tracking.
- **Cross-Chain Transfers:** `cross_chain_transfer()` for CCTP-based transfers via Squid Router.
- **`smart_fetch()`** — Auto-negotiate 402 paywalls with retry logic.
- **`AsyncModexiaClient`** — Full async mirror using `httpx` for swarm-style concurrency.
- **Transaction History:** `get_history()` with `TransactionHistoryItem` and `TransactionHistoryResponse` dataclasses.

---

## [0.5.0] - 2026-03-01

### Added

- Initial public release.
- `ModexiaClient` with `transfer()`, `retrieve_balance()`, `get_balance()`.
- API key validation and environment detection (`mx_test_` / `mx_live_`).
- Built-in retry logic with exponential backoff.
- `PaymentReceipt` dataclass.
