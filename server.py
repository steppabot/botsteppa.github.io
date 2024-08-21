from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import stripe
import uuid
import os
import logging
import requests  # To make API requests to Discord
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_url_path='/static')
CORS(app)  # Enable CORS for all routes

# Load API keys from environment variables
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Route for serving static files
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

def get_discord_username(user_id):
    app.logger.info(f"Fetching username for User ID: {user_id}")
    url = f"https://discord.com/api/v10/users/{user_id}"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}"
    }
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        user_data = response.json()
        # Prefer global_name if it exists, otherwise fall back to username
        return user_data.get("global_name") or user_data.get("username")
    else:
        app.logger.error(f"Failed to fetch username for User ID: {user_id}. Response: {response.text}")
        return None

@app.route('/username/<user_id>', methods=['GET'])
def get_username(user_id):
    username = get_discord_username(user_id)
    if username:
        return jsonify({"username": username})
    else:
        return jsonify({"error": "User not found"}), 404

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        data = request.json
        discord_id = data.get('discordId')

        unique_id = str(uuid.uuid4())

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f'Donation-{unique_id}',
                    },
                    'unit_amount': 500,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url='https://discord.com/channels/978953837022937138/978953837022937141',
            cancel_url='https://discord.com/channels/978953837022937138/978953837022937141'
        )
        print(f"Created Stripe session with ID: {session.id}")
        print(session.url)
        response = jsonify({'id': session.id})
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    except Exception as e:
        return jsonify(error=str(e)), 400

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)  # Set to DEBUG for detailed logs
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
