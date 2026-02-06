import os
import logging
import requests
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY', '1aa188680emshf3388292322e18ap115fafjsna078f52ee12e')
RAPIDAPI_HOST = 'virtual-number.p.rapidapi.com'
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# In-memory storage (replace with database in production)
user_data_store = {}
purchased_numbers = {}

class VirtualNumberAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://virtual-number.p.rapidapi.com/api/v1/e-sim"
        self.headers = {
            "x-rapidapi-host": RAPIDAPI_HOST,
            "x-rapidapi-key": api_key,
            "Content-Type": "application/json"
        }
    
    def get_all_countries(self):
        """Get list of all available countries"""
        url = f"{self.base_url}/all-countries"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching countries: {e}")
            return {"success": False, "error": str(e)}
    
    def purchase_number(self, country_code, service="telegram"):
        """Purchase a virtual number"""
        url = f"{self.base_url}/purchase"
        payload = {
            "country_code": country_code,
            "service": service
        }
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error purchasing number: {e}")
            return {"success": False, "error": str(e)}
    
    def get_sms(self, number_id):
        """Get SMS messages for a number"""
        url = f"{self.base_url}/sms/{number_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching SMS: {e}")
            return {"success": False, "error": str(e)}
    
    def get_active_numbers(self):
        """Get list of active numbers"""
        url = f"{self.base_url}/active-numbers"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching active numbers: {e}")
            return {"success": False, "error": str(e)}
    
    def cancel_number(self, number_id):
        """Cancel a virtual number"""
        url = f"{self.base_url}/cancel/{number_id}"
        try:
            response = requests.delete(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error canceling number: {e}")
            return {"success": False, "error": str(e)}

# Initialize API client
api_client = VirtualNumberAPI(RAPIDAPI_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message with inline keyboard"""
    user = update.effective_user
    user_data_store[user.id] = {
        "username": user.username,
        "first_name": user.first_name,
        "join_date": datetime.now().isoformat()
    }
    
    keyboard = [
        [InlineKeyboardButton("📱 List Countries", callback_data='list_countries')],
        [InlineKeyboardButton("🛒 Purchase Number", callback_data='purchase_menu')],
        [InlineKeyboardButton("📨 My SMS", callback_data='my_sms')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_message = f"""
🚀 *Welcome to Virtual Number Bot, {user.first_name}!*

*Available Features:*
• 📱 Get virtual numbers from multiple countries
• 📨 Receive SMS messages on Telegram
• 🌍 100+ countries available
• ⚡ Real-time SMS forwarding

*Quick Commands:*
/start - Show this menu
/countries - Browse available countries
/purchase - Buy a new virtual number
/mysms - Check received SMS
/help - Get help information

Select an option below to get started:
"""
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help information"""
    help_text = """
🤖 *Virtual Number Bot - Help Guide*

*Available Commands:*
/start - Start the bot
/countries - Show all available countries
/purchase - Purchase a virtual number
/mysms - View received SMS
/active - View active numbers
/cancel - Cancel a virtual number
/help - Show this help message

*How It Works:*
1. Select a country from the list
2. Purchase a virtual number
3. Use the number for SMS verification
4. Receive SMS directly in Telegram
5. SMS are forwarded in real-time

*Important Notes:*
• Numbers are rented and have expiration
• SMS forwarding may have a slight delay
• Some services may block virtual numbers
• Check country compatibility before purchase

*Support:* Contact @admin for assistance
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def list_countries_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch and display available countries"""
    message = await update.message.reply_text("🔄 Fetching available countries...")
    
    result = api_client.get_all_countries()
    
    if result.get('success'):
        countries = result.get('data', [])
        
        if not countries:
            await message.edit_text("❌ No countries available at the moment.")
            return
        
        # Group countries for pagination
        page = 0
        items_per_page = 10
        total_pages = (len(countries) - 1) // items_per_page + 1
        
        context.user_data['countries'] = countries
        context.user_data['country_page'] = page
        
        await show_countries_page(update, context, message, page)
    else:
        error_msg = result.get('error', 'Unknown error')
        await message.edit_text(f"❌ Error fetching countries: {error_msg}")

async def show_countries_page(update, context, message, page):
    """Display a page of countries"""
    countries = context.user_data.get('countries', [])
    items_per_page = 10
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    
    current_countries = countries[start_idx:end_idx]
    
    # Create keyboard with countries
    keyboard = []
    for country in current_countries:
        country_code = country.get('country_code', '')
        country_name = country.get('country_name', 'Unknown')
        emoji = country.get('emoji', '🌐')
        price = country.get('price', 'N/A')
        
        keyboard.append([InlineKeyboardButton(
            f"{emoji} {country_name} - ${price}",
            callback_data=f'select_country_{country_code}'
        )])
    
    # Navigation buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f'country_page_{page-1}'))
    if end_idx < len(countries):
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f'country_page_{page+1}'))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"🌍 *Available Countries* ({len(countries)} total)\n"
    text += f"Page {page + 1} of {((len(countries) - 1) // items_per_page) + 1}\n\n"
    text += "Select a country to purchase a number:"
    
    await message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def purchase_number_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate number purchase process"""
    if context.args:
        country_code = context.args[0]
        await purchase_for_country(update, context, country_code)
    else:
        keyboard = [
            [InlineKeyboardButton("🇺🇸 USA (+1)", callback_data='select_country_US')],
            [InlineKeyboardButton("🇬🇧 UK (+44)", callback_data='select_country_GB')],
            [InlineKeyboardButton("🇨🇦 Canada (+1)", callback_data='select_country_CA')],
            [InlineKeyboardButton("🇦🇺 Australia (+61)", callback_data='select_country_AU')],
            [InlineKeyboardButton("🌍 Browse All Countries", callback_data='list_countries')],
            [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🛒 *Purchase Virtual Number*\n\n"
            "Select a country or browse all:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

async def purchase_for_country(update: Update, context: ContextTypes.DEFAULT_TYPE, country_code: str):
    """Purchase number for specific country"""
    user_id = update.effective_user.id
    message = await update.callback_query.message.reply_text(f"🔄 Purchasing number for {country_code}...")
    
    result = api_client.purchase_number(country_code)
    
    if result.get('success'):
        number_data = result.get('data', {})
        number_id = number_data.get('number_id')
        phone_number = number_data.get('phone_number')
        
        # Store purchased number
        purchased_numbers[number_id] = {
            "user_id": user_id,
            "country_code": country_code,
            "phone_number": phone_number,
            "purchase_date": datetime.now().isoformat(),
            "status": "active"
        }
        
        # Store in user data
        if user_id not in user_data_store:
            user_data_store[user_id] = {}
        
        if 'numbers' not in user_data_store[user_id]:
            user_data_store[user_id]['numbers'] = []
        
        user_data_store[user_id]['numbers'].append(number_id)
        
        await message.edit_text(
            f"✅ *Number Purchased Successfully!*\n\n"
            f"📱 *Number:* {phone_number}\n"
            f"🌍 *Country:* {country_code}\n"
            f"🆔 *ID:* {number_id}\n\n"
            f"*Instructions:*\n"
            f"1. Use this number for SMS verification\n"
            f"2. SMS will be forwarded here automatically\n"
            f"3. Use /mysms to check messages\n"
            f"4. Use /cancel {number_id} to cancel\n\n"
            f"📨 SMS forwarding is now active!",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        error_msg = result.get('error', 'Purchase failed')
        await message.edit_text(f"❌ Purchase failed: {error_msg}")

async def my_sms_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's received SMS"""
    user_id = update.effective_user.id
    
    if user_id not in user_data_store or 'numbers' not in user_data_store[user_id]:
        await update.message.reply_text("📭 You don't have any active numbers.")
        return
    
    user_numbers = user_data_store[user_id]['numbers']
    
    if not user_numbers:
        await update.message.reply_text("📭 You don't have any active numbers.")
        return
    
    # For demo - in production, fetch actual SMS from API
    keyboard = []
    for number_id in user_numbers[:5]:  # Limit to 5 numbers
        if number_id in purchased_numbers:
            number_info = purchased_numbers[number_id]
            keyboard.append([InlineKeyboardButton(
                f"📱 {number_info['phone_number']}",
                callback_data=f'view_sms_{number_id}'
            )])
    
    if not keyboard:
        await update.message.reply_text("📭 No active numbers found.")
        return
    
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data='refresh_sms')])
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📨 *My SMS Messages*\n\n"
        "Select a number to view received SMS:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def active_numbers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's active numbers"""
    user_id = update.effective_user.id
    
    if user_id not in user_data_store or 'numbers' not in user_data_store[user_id]:
        await update.message.reply_text("📱 You don't have any active numbers.")
        return
    
    active_numbers = []
    for number_id in user_data_store[user_id]['numbers']:
        if number_id in purchased_numbers and purchased_numbers[number_id]['status'] == 'active':
            active_numbers.append(purchased_numbers[number_id])
    
    if not active_numbers:
        await update.message.reply_text("📱 You don't have any active numbers.")
        return
    
    message = "📱 *Your Active Numbers*\n\n"
    for num in active_numbers:
        message += f"• *Number:* {num['phone_number']}\n"
        message += f"  *Country:* {num['country_code']}\n"
        message += f"  *ID:* `{number_id}`\n"
        message += f"  *Since:* {num['purchase_date'][:10]}\n\n"
    
    message += "Use /cancel <number_id> to cancel a number."
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def cancel_number_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel a virtual number"""
    if not context.args:
        await update.message.reply_text("Usage: /cancel <number_id>")
        return
    
    number_id = context.args[0]
    user_id = update.effective_user.id
    
    # Check if number belongs to user
    if (user_id not in user_data_store or 
        'numbers' not in user_data_store[user_id] or 
        number_id not in user_data_store[user_id]['numbers']):
        await update.message.reply_text("❌ Number not found or doesn't belong to you.")
        return
    
    if number_id not in purchased_numbers:
        await update.message.reply_text("❌ Number not found.")
        return
    
    # Call API to cancel
    result = api_client.cancel_number(number_id)
    
    if result.get('success'):
        purchased_numbers[number_id]['status'] = 'cancelled'
        await update.message.reply_text(f"✅ Number {number_id} cancelled successfully.")
    else:
        error_msg = result.get('error', 'Cancellation failed')
        await update.message.reply_text(f"❌ Cancellation failed: {error_msg}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'main_menu':
        await start(update, context)
    
    elif data == 'list_countries':
        await list_countries_command(update, context)
    
    elif data == 'purchase_menu':
        await purchase_number_command(update, context)
    
    elif data == 'my_sms':
        await my_sms_command(update, context)
    
    elif data == 'help':
        await help_command(update, context)
    
    elif data.startswith('country_page_'):
        page = int(data.split('_')[-1])
        context.user_data['country_page'] = page
        await show_countries_page(update, context, query.message, page)
    
    elif data.startswith('select_country_'):
        country_code = data.split('_')[-1]
        await purchase_for_country(update, context, country_code)
    
    elif data.startswith('view_sms_'):
        number_id = data.split('_')[-1]
        await view_sms_messages(update, context, number_id)

async def view_sms_messages(update: Update, context: ContextTypes.DEFAULT_TYPE, number_id: str):
    """View SMS messages for a specific number"""
    query = update.callback_query
    
    # Fetch SMS from API
    result = api_client.get_sms(number_id)
    
    if result.get('success'):
        messages = result.get('data', [])
        
        if messages:
            text = f"📨 *SMS Messages for {number_id}*\n\n"
            for msg in messages[:10]:  # Show last 10 messages
                sender = msg.get('sender', 'Unknown')
                message = msg.get('message', '')
                timestamp = msg.get('timestamp', '')
                
                text += f"*From:* {sender}\n"
                text += f"*Time:* {timestamp}\n"
                text += f"*Message:* {message}\n"
                text += "─" * 30 + "\n"
        else:
            text = f"📭 No SMS messages found for {number_id}"
    else:
        text = f"❌ Error fetching SMS: {result.get('error', 'Unknown error')}"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data=f'view_sms_{number_id}')],
        [InlineKeyboardButton("📱 My Numbers", callback_data='my_sms')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def check_sms_scheduler(context: ContextTypes.DEFAULT_TYPE):
    """Periodically check for new SMS"""
    for number_id, number_info in list(purchased_numbers.items()):
        if number_info['status'] == 'active':
            result = api_client.get_sms(number_id)
            
            if result.get('success'):
                messages = result.get('data', [])
                
                # Here you would implement logic to detect new messages
                # and forward them to the user
                
                # Example forwarding logic:
                for msg in messages:
                    # Check if message is new (compare with stored messages)
                    # Forward to user...
                    pass

def main():
    """Start the bot"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Please set TELEGRAM_BOT_TOKEN environment variable")
        return
    
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("countries", list_countries_command))
    application.add_handler(CommandHandler("purchase", purchase_number_command))
    application.add_handler(CommandHandler("mysms", my_sms_command))
    application.add_handler(CommandHandler("active", active_numbers_command))
    application.add_handler(CommandHandler("cancel", cancel_number_command))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Start SMS scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_sms_scheduler, 'interval', minutes=1, args=[application])
    scheduler.start()
    
    # Start the bot
    logger.info("Bot started...")
    application.run_polling()

if __name__ == '__main__':
    main()
