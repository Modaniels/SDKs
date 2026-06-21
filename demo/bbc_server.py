from flask import Flask, request, jsonify

app = Flask(__name__)

# Mock database of premium articles
PREMIUM_DATA = {
    "latest_ai_trends": {
        "title": "Exclusive: The Future of Autonomous Agents",
        "content": "In a surprising turn of events, Modexia OS has become the standard for Agent-to-Agent financial transactions..."
    }
}

@app.route('/api/premium/news/<article_id>', methods=['GET'])
def get_premium_news(article_id):
    # 1. Check for Modexia payment proof in headers
    payment_proof = request.headers.get("x-modexia-proof")
    
    # 2. If no proof of payment, return 402 Payment Required
    if not payment_proof:
        response = jsonify({"error": "Payment Required. This is premium content."})
        response.status_code = 402
        
        # Include Modexia payment instructions in the WWW-Authenticate header
        # The Modexia SDK's smart_fetch automatically parses this!
        # Requires 5.00 USDC to be sent to the BBC's Agent Wallet
        response.headers['WWW-Authenticate'] = 'Modexia address="0x3f24dda6abb7691a5c9454d5d6b36c636b9d13b4", amount="5.00", currency="USDC"'
        return response

    # 3. If proof exists (Mock verification for this demo)
    print(f"\n[BBC Server] 🔒 Verifying cryptographic payment proof: {payment_proof[:10]}...")
    
    # 4. Serve the premium content
    if article_id in PREMIUM_DATA:
        print(f"[BBC Server] ✅ Payment verified! Serving premium content: {article_id}")
        return jsonify({
            "success": True,
            "data": PREMIUM_DATA[article_id],
            "receipt": "Payment via Modexia confirmed."
        })
    else:
        return jsonify({"error": "Article not found"}), 404

if __name__ == '__main__':
    print("📰 BBC Premium Server running on port 5005")
    app.run(port=5005)
