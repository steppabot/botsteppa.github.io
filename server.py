from quart import Quart, jsonify, request, send_from_directory
from quart_cors import cors
import discord
import os
import logging
import stripe
import uuid
import aiohttp
import json
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
                time.sleep(retry_after)
                return await get_discord_username(user_id)
            else:
                app.logger.error(f"Failed to fetch username for User ID: {user_id}. Status: {response.status}")
                return None

async def update_usernames_in_json():
    try:
        # Load the JSON file
        with open('static/july2024.json', 'r') as f:
            data = json.load(f)

        # Filter out users missing the 'steps' key
        valid_data = {user_id: user_data for user_id, user_data in data.items() if 'steps' in user_data}

        if not valid_data:
            app.logger.error("No valid users found with 'steps' key.")
            return

        # Sort and get top 3 users by steps and miles
        users_by_steps = sorted(valid_data.items(), key=lambda item: item[1].get('steps', 0), reverse=True)[:3]
        users_by_miles = sorted(valid_data.items(), key=lambda item: item[1].get('miles', 0), reverse=True)[:3]

        # Combine the two lists and remove duplicates
        top_users = {user_id: user_data for user_id, user_data in users_by_steps + users_by_miles}

        # Iterate over the top user IDs and fetch usernames
        for user_id, user_data in top_users.items():
            if not user_data.get('username'):  # Check if username is blank
                username = await get_discord_username(user_id)
                if username:
                    user_data['username'] = username
                    print(f"Updated username for {user_id}: {username}")
                    # Update the original data
                    data[user_id]['username'] = username
                await asyncio.sleep(1)  # Sleep for 1 second between requests
        
        # Write back the updated data to the JSON file
        with open('static/july2024.json', 'w') as f:
            json.dump(data, f, indent=4)

    except Exception as e:
        app.logger.error(f"Error updating usernames in JSON: {e}")


# Call this function when the server starts to ensure the JSON file is updated
@app.before_serving
async def before_serving():
    await update_usernames_in_json()

# API endpoint to fetch username (optional, depending on your needs)
@app.route('/username/<user_id>', methods=['GET'])
async def get_username(user_id):
    try:
        # Load the JSON file
        with open('static/july2024.json', 'r') as f:
            data = json.load(f)

        # Fetch the username if it's present
        user_data = data.get(user_id)
        if user_data and 'username' in user_data:
            return jsonify({"username": user_data['username']})
        else:
            # Fetch from Discord and update the JSON
            username = await get_discord_username(user_id)
            if username:
                data[user_id]['username'] = username
                with open('static/july2024.json', 'w') as f:
                    json.dump(data, f, indent=4)
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

# Stripe checkout session creation
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
    port = int(os.environ.get('PORT', 5000))  # Use PORT provided by Heroku or default to 5000
    app.run(host='0.0.0.0', port=port)  # Bind to 0.0.0.0 to accept connections from outside
