from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class PaymentReceipt:
    success: bool
    status: str
    txId: Optional[str] = None
    txHash: Optional[str] = None
    errorReason: Optional[str] = None
    
@dataclass
class TransactionHistoryItem:
    txId: str
    type: str
    amount: str
    state: str
    createdAt: str
    providerAddress: Optional[str] = None
    txHash: Optional[str] = None
    
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
