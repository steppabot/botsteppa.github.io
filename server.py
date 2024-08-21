from quart import Quart, jsonify, request
from quart_cors import cors
import discord
import os
import logging
import stripe
import uuid
import requests
from dotenv import load_dotenv

load_dotenv()

# Quart app setup
app = Quart(__name__)
app = cors(app)  # Enable CORS for all routes

# Initialize the Discord client with intents
intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)

# Load the Discord Bot Token
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Function to get Discord username using discord.py
async def fetch_discord_username(user_id):
    user = await client.fetch_user(user_id)
    return user.global_name or user.name

# Route to get the username
@app.route('/username/<user_id>', methods=['GET'])
async def get_username(user_id):
    try:
        username = await fetch_discord_username(int(user_id))
        if username:
            return jsonify({"username": username})
        else:
            return jsonify({"error": "User not found"}), 404
    except Exception as e:
        app.logger.error(f"Failed to fetch username for User ID: {user_id}. Error: {e}")
        return jsonify({"error": "An error occurred"}), 500

# Route for serving static files
@app.route('/static/<path:filename>')
async def serve_static(filename):
    return await send_from_directory('static', filename)

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
