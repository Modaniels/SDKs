from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class PaymentReceipt:
    success: bool
    status: str
    txId: Optional[str] = None
    txHash: Optional[str] = None
    errorReason: Optional[str] = None
    txIds: Optional[List[str]] = None
    axelarScanUrls: Optional[List[str]] = None

    @property
    def squidStatusUrls(self) -> Optional[List[str]]:
        """Deprecated: use axelarScanUrls instead."""
        return self.axelarScanUrls

    
@dataclass
class TransactionHistoryItem:
    txId: str
    type: str
    amount: str
    state: str
    createdAt: str
    providerAddress: Optional[str] = None
    txHash: Optional[str] = None
    memo: Optional[str] = None
    
@dataclass
class TransactionHistoryResponse:
    transactions: List[TransactionHistoryItem]
    hasMore: bool

@dataclass
class ChannelReceipt:
    """HMAC-signed receipt returned by each off-chain consume call."""
    channelId: str
    cumulativeTotal: str
    nonce: int
    hmac: str
    timestamp: int = 0

@dataclass
class ConsumeResponse:
    """Result of a single micro-payment inside a payment channel."""
    success: bool
    receipt: ChannelReceipt
    remaining: str
    isDuplicate: bool = False

@dataclass
class ChannelStatus:
    """Current state of a payment channel."""
    channelId: str
    providerAddress: str
    deposit: str
    cumulativePaid: str
    remaining: str
    consumeCount: int
    expiry: str
    state: str
    isExpired: bool = False


@dataclass
class IntentResult:
    """Rich result returned from the v2 intent-to-pay pipeline.

    Contains the intent status, transaction details (if executed),
    compliance/validation metadata, and actionable suggestions on rejection.
    """
    status: str                          # pending | approved | rejected | executed | failed
    intent_id: Optional[str] = None
    # Transaction details (populated on 'executed')
    txId: Optional[str] = None
    txIds: Optional[List[str]] = None
    txState: Optional[str] = None
    amount: Optional[str] = None
    recipient: Optional[str] = None
    # Compliance & policy metadata
    wallet_balance_after: Optional[str] = None
    daily_spent: Optional[str] = None
    daily_remaining: Optional[str] = None
    # Rejection info
    reason: Optional[str] = None
    code: Optional[str] = None
    suggestion: Optional[str] = None
    # Full validation pipeline results
    validation: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
#  NANOPAY — Circle Gateway Nanopayment models
# ═══════════════════════════════════════════════════════════════════

@dataclass
class NanopayBalance:
    """Circle Gateway Wallet balance.

    Returned by ``ModexiaClient.nanopay_balance()``.
    The Gateway balance is separate from the agent's main SCA wallet balance.
    """
    available: str          # Available for nanopayments (USDC)
    total: str              # Total deposited (USDC)
    withdrawing: str        # Currently being withdrawn (USDC)
    withdrawable: str       # Ready to withdraw (USDC)
    auto_refill_enabled: bool = False
    auto_refill_threshold: Optional[str] = None
    auto_refill_amount: Optional[str] = None


@dataclass
class NanopayDepositResult:
    """Result of depositing USDC into the Circle Gateway.

    Returned by ``ModexiaClient.nanopay_deposit(amount)``.
    The deposit is an on-chain transaction that moves USDC from the agent's
    SCA wallet into the Gateway Wallet contract.
    """
    success: bool
    deposit_tx_id: Optional[str] = None
    amount: Optional[str] = None
    gateway_balance_after: Optional[NanopayBalance] = None


@dataclass
class NanopayWithdrawResult:
    """Result of withdrawing USDC from the Circle Gateway.

    Returned by ``ModexiaClient.nanopay_withdraw(amount)``.
    """
    success: bool
    withdraw_tx_id: Optional[str] = None
    amount: Optional[str] = None


@dataclass
class NanopayResult:
    """Result of an x402 nanopayment transaction.

    Returned by ``ModexiaClient.nanopay(url)``.
    Contains both the HTTP response data from the x402 resource
    and the payment metadata (how much was paid, transfer status, etc.).
    """
    success: bool
    status_code: int                     # HTTP status of the final response
    data: Any = None                     # The actual resource data
    amount_paid: Optional[str] = None    # How much USDC was paid
    signature: Optional[str] = None      # The EIP-3009 signature used
    gateway_balance: Optional[NanopayBalance] = None
