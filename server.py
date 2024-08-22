from quart import Quart, jsonify, request, send_from_directory, redirect
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

# Stripe API key
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

# Dictionary to store user IDs and usernames
usernames_dict = {}

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
            else:
                app.logger.error(f"Failed to fetch username for User ID: {user_id}. Status: {response.status}")
                return None

async def update_usernames():
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
            if user_id not in usernames_dict:  # Check if username is already fetched
                username = await get_discord_username(user_id)
                if username:
                    usernames_dict[user_id] = username
                    print(f"Fetched and stored username for {user_id}: {username}")
                else:
                    usernames_dict[user_id] = "Unknown User"
                await asyncio.sleep(1)  # Sleep for 1 second between requests

    except Exception as e:
        app.logger.error(f"Error fetching usernames: {e}")

@app.before_serving
async def before_serving():
    await update_usernames()

@app.route('/')
async def index():
    # You can either serve an index page, or simply redirect to /hof
    return redirect('/hof')

@app.route('/hof', methods=['GET'])
async def get_hall_of_fame():
    try:
        # Log the start of the process
        app.logger.info("Starting to load the Hall of Fame data...")

        # Load the JSON file
        with open('static/july2024.json', 'r') as f:
            data = json.load(f)
            app.logger.info("Successfully loaded JSON data: %s", data)

        # Ensure that `usernames_dict` is populated
        app.logger.info("Current usernames_dict: %s", usernames_dict)

        # Replace user IDs with usernames from the dictionary
        for user_id, user_data in data.items():
            if user_id in usernames_dict:
                user_data['username'] = usernames_dict[user_id]
            else:
                user_data['username'] = "Unknown User"

        app.logger.info("Successfully processed Hall of Fame data: %s", data)
        return jsonify(data)
        
    except FileNotFoundError:
        app.logger.error("july2024.json file not found.")
        return jsonify({"error": "JSON file not found"}), 404
        
    except json.JSONDecodeError as e:
        app.logger.error(f"JSON Decode Error: {str(e)}")
        return jsonify({"error": "Invalid JSON format"}), 500
    
    except Exception as e:
        app.logger.error(f"General Error: {str(e)}")
        return jsonify({"error": "An error occurred"}), 500

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
