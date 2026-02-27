from dataclasses import dataclass
from typing import Optional, List, Dict, Any

@dataclass
class IdentityResponse:
    username: str
    balance: str
    walletAddress: Optional[str] = None
    email: Optional[str] = None
    
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
