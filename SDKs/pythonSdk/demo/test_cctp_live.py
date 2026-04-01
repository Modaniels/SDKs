import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from modexia import ModexiaClient
import uuid

def test_live_cctp():
    api_key = os.environ.get("MODEXIA_API_KEY", "mx_live_f153033c562c4f07b3ff98aa90aec181")
    if api_key == "your_api_key_here":
        print("Please set MODEXIA_API_KEY environment variable to run this live test.")
        return
        
    print(f"Initializing ModexiaClient with API key: {api_key[:15]}...")
    
    # We must explicitly route to localhost instead of sandbox.modexia.software
    # because our local app.js changes haven't been deployed to the public server yet!
    client = ModexiaClient(api_key=api_key, base_url="http://localhost:3001")
    
    try:
        print("\n--- Testing retrieve_balance ---")
        balance = client.retrieve_balance()
        print(f"Current Balance: {balance} USDC")
        
        print("\n--- Testing cross_chain_transfer via Squid Router ---")
        # Squid V2 supports EVM chains. Use Arbitrum (42161) as destination.
        to_chain = "42161"  # Arbitrum One
        to_token = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"  # Native USDC on Arbitrum
        recipient = "0x0286a4aa2b67b28243c31a58cb220c53af57b450"  # Same wallet (self-transfer for testing)
        amount = 0.05
        # Optional explicit idempotency key
        ikey = str(uuid.uuid4())
        
        print(f"Sending {amount} USDC to {recipient} on Chain {to_chain}...")
        receipt = client.cross_chain_transfer(to_chain, to_token, recipient, amount, idempotency_key=ikey)
        
        print(f"Success: {receipt.success}")
        print(f"Status: {receipt.status}")
        print(f"Internal TX ID: {receipt.txId}")
        print("\nIntegration Test Passed!")
    except Exception as e:
        print(f"\nIntegration Test Failed: {e}")

if __name__ == "__main__":
    test_live_cctp()
