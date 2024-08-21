from quart import Quart, jsonify, request, send_from_directory
from quart_cors import cors
import discord
import os
import logging
import stripe
import uuid
import aiohttp
import json
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Quart app setup
app = Quart(__name__)
app = cors(app, allow_origin="*")

# Initialize the Discord client with intents
intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)

# Load the Discord Bot Token
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

async def get_discord_username(user_id):
    url = f"https://discord.com/api/v10/users/{user_id}"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                app.logger.info(f"Discord API response for user {user_id}: {data}")
                return data.get("global_name") or data.get("username")
            elif response.status == 429:
                retry_after = int(response.headers.get("Retry-After", 1))
                app.logger.error(f"Rate limit hit for User ID: {user_id}. Retrying after {retry_after} seconds.")
                await asyncio.sleep(retry_after)
                return await get_discord_username(user_id)
            else:
                app.logger.error(f"Failed to fetch username for User ID: {user_id}. Status: {response.status}")
                return None

@app.route('/hof', methods=['GET'])
async def get_hall_of_fame():
    try:
        # Load the JSON file
        with open('static/july2024.json', 'r') as f:
            data = json.load(f)

        app.logger.info("Loaded JSON data successfully.")

        # Identify the top 3 users by steps and miles
        users_by_steps = sorted(data.items(), key=lambda item: item[1].get('steps', 0), reverse=True)[:3]
        users_by_miles = sorted(data.items(), key=lambda item: item[1].get('miles', 0), reverse=True)[:3]

        app.logger.info(f"Top 3 users by steps: {users_by_steps}")
        app.logger.info(f"Top 3 users by miles: {users_by_miles}")

        # Combine the top steppers and top miles, avoiding duplicates
        top_users = {user_id: user_data for user_id, user_data in users_by_steps + users_by_miles}

        # Fetch usernames if missing
        for user_id, user_data in top_users.items():
            if not user_data.get('username'):
                username = await get_discord_username(user_id)
                if username:
                    user_data['username'] = username
                else:
                    user_data['username'] = "Unknown User"
                app.logger.info(f"Updated username for {user_id}: {user_data['username']}")
                await asyncio.sleep(1)  # Respect rate limits

        # Prepare the response data
        response_data = {
            "top_steppers": [{"username": user_data['username'], "steps": user_data['steps']} for user_id, user_data in users_by_steps],
            "top_miles": [{"username": user_data['username'], "miles": round(user_data['miles'])} for user_id, user_data in users_by_miles],
        }

        app.logger.info(f"Response data: {response_data}")

        return jsonify(response_data)

    except Exception as e:
        app.logger.error(f"Error generating Hall of Fame: {e}")
        return jsonify({"error": "Failed to generate Hall of Fame"}), 500

# Route for serving static files
@app.route('/static/<path:filename>')
async def serve_static(filename):
    return await send_from_directory('static', filename)

# Stripe checkout session creation
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        data = request.json
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
        response = jsonify({'id': session.id})
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    except Exception as e:
        return jsonify(error=str(e)), 400

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
