import time
import os
from modexia import ModexiaClient



def simulate_agent_transfer():
    print("\n=======================================================")
    print("🤖 AI Research Agent - News Gathering Mode")
    print("=======================================================\n")
    
    print(" [Research Agent] Initializing Modexia wallet...")
    try:
        # SDK is initialized using the provided API Key for the test environment
        api_key = os.environ.get("MODEXIA_API_KEY", "mx_test_YOUR_KEY_HERE")
        client = ModexiaClient(api_key=api_key)
        time.sleep(1)
        print(" [Research Agent] Modexia wallet connected.")
        
        balance = client.retrieve_balance()
        print(f" [Research Agent] Current Balance: {balance} USDC")
    except Exception as e:
        print(f" [Research Agent] Failed to connect: {str(e)}")
        return
        
    print("\n [Research Agent] Objective: Fetching the latest premium AI trends report from BBC API...")
    target_url = "https://api.bbc.co.uk/premium/news/latest_ai_trends"
    time.sleep(1.5)
    
    print(f" [Research Agent] Making GET request to {target_url}...")
    time.sleep(1)
    
    print("\n [Research Agent] HTTP 402 Payment Required intercepted.")
    print("🔍 [Research Agent] Parsing WWW-Authenticate header from response...")
    time.sleep(1)
    
    amount_required = 4.67
    bbc_wallet = "0x3f24dda6abb7691a5c9454d5d6b36c636b9d13b4"
    print(f" [Research Agent] BBC API requires {amount_required} USDC to wallet: {bbc_wallet}")
    print(" [Research Agent] Authorizing payment via Modexia OS...")
    time.sleep(1)

    print(f" [Modexia] Initiating on-chain transfer of {amount_required} USDC...")
    try:
        # Make the actual real transfer using the Modexia SDK
        receipt = client.transfer(
            recipient=bbc_wallet,
            amount=amount_required,
            wait=True,
            idempotency_key=f"bbc_report_{int(time.time())}"
        )
        
        if receipt.success:
            print(f" [Modexia] Payment confirmed on-chain!")
            print(f" [Modexia] TxHash: {receipt.txHash}")
            print(f" [Modexia] Payment Proof generated.")
        else:
            print(f" [Modexia] Transaction completed but flagged as unsuccessful: {receipt}")
            return
            
    except Exception as e:
        print(f" [Modexia] Payment failed: {e}")
        return
        
    print(" [Research Agent] Retrying GET request with Modexia Payment Proof (x-modexia-proof)...")
    time.sleep(2)
    
    print("[Research Agent] Request successful! Premium Data received:")
    print("\n-------------------------------------------------------")
    print(f" TITLE:   Exclusive: The Future of Autonomous Agents")
    print(f" CONTENT: In a surprising turn of events, Modexia OS has become the standard for Agent-to-Agent financial transactions. Agents are now seamlessly exchanging value, breaking down paywalls, and creating a truly autonomous economic layer on the internet...")
    print("-------------------------------------------------------\n")
    print(" [Research Agent] Mission accomplished. Shutting down.\n")
    print("=======================================================\n")

if __name__ == "__main__":
    simulate_agent_transfer()
