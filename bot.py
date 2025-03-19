import os
import time
import asyncio
import requests
import sqlite3
import logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from utils import (
    get_bnb_balance,
    get_token_balances,
    get_last_transactions,
    get_bnb_price
)
from config import TELEGRAM_BOT_TOKEN, BSCSCAN_API_KEY
from db import init_db, add_wallet, remove_wallet, get_wallets, add_seen_tx, get_seen_txs, update_wallet_name
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize the database
init_db()

# ========== Global Variables ==========
USER_WATCH_TASKS = {}  # Format: {chat_id: {wallet_address: task}}, for managing active tasks
last_refresh_time = {}

# ========== Message Templates ==========
WELCOME_MESSAGE = """
🚀 Welcome to *BSCApeTracker*!  
Your #1 BSC wallet tracker on Telegram! 🏆💼  

🔍 Easily monitor your wallet, track transactions, and stay updated on your holdings.  

📌 Click /help to view all available commands.
"""

HELP_MESSAGE = """📌 <b>Available Commands:</b>\n
🔹 <b>General Commands:</b>
/start - Start the bot
/help - Show this help message

🔹 <b>Wallet Tracking Commands:</b>
/profile <code>&lt;wallet_address&gt;</code> - View wallet portfolio
/watch <code>&lt;wallet_address&gt;</code> - Start watching a wallet
/watched - List watched wallets
/stopwatch <code>&lt;wallet_address&gt;</code> - Stop watching a wallet
"""

# ========== Helper Functions ==========
def get_wallet_display(chat_id: int, wallet_address: str) -> str:
    """Get the display name for a wallet; use custom name if set, otherwise wallet address."""
    wallets = get_wallets(chat_id)
    for wallet, custom_name in wallets:
        if wallet == wallet_address and custom_name:
            return custom_name  # Show only the custom name if it exists
    return wallet_address  # Default to address if no custom name

# ========== Command Handlers ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message to the user."""
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display the list of available commands."""
    await update.message.reply_text(HELP_MESSAGE, parse_mode="HTML", disable_web_page_preview=True)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the portfolio for a given wallet address."""
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a wallet address.\nExample: `/profile 0x123...`",
            parse_mode="Markdown"
        )
        return

    wallet_address = context.args[0]
    chat_id = update.effective_chat.id
    message_text, reply_markup = await generate_profile_message(chat_id, wallet_address, is_refresh=False)
    await update.message.reply_text(
        message_text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )

async def generate_profile_message(chat_id: int, wallet_address: str, is_refresh=False):
    """Generate the portfolio message for a wallet using its display name."""
    display_name = get_wallet_display(chat_id, wallet_address)
    native_bnb = get_bnb_balance(wallet_address)
    bnb_price = get_bnb_price()
    bnb_usd_value = float(native_bnb) * float(bnb_price)
    
    all_tokens = get_token_balances(wallet_address)
    filtered_tokens = [token for token in all_tokens if token["balance"] > 0 and token["symbol"].upper() != "BNB"]
    display_tokens = filtered_tokens[:10] if len(filtered_tokens) > 10 else filtered_tokens
    
    message = f"📊 *Portfolio for {display_name}*\n\n"
    message += f"💰 *BNB Balance:* {native_bnb:,.7f} BNB (~${bnb_usd_value:,.2f} USD)\n\n"
    message += f"🔢 *Tokens Held:* {len(filtered_tokens):,}\n"
    for token in display_tokens:
        message += f"• {token['symbol']}: {token['balance']:,.2f}\n"
    
    last_transactions = get_last_transactions(wallet_address)
    for tx_type, emoji in [("buy", "🟢"), ("sell", "🔴")]:
        if tx := last_transactions.get(tx_type):
            tx_time = datetime.fromtimestamp(tx["timestamp"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            message += f"\n{emoji} *Last {tx_type.capitalize()}:*\n"
            message += f"• Token: {tx['symbol']}\n"
            message += f"• Amount: {tx['amount']:,.2f}\n"
            message += f"• Timestamp: {tx_time}\n"
            message += f"• [View Transaction](https://bscscan.com/tx/{tx['tx_hash']})\n"
    
    if is_refresh:
        refresh_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        message += f"\n🕒 *Last Refreshed:* {refresh_time}\n"

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_profile:{wallet_address}")],
        [
            InlineKeyboardButton("👀 Watch Wallet", callback_data=f"watch_wallet:{wallet_address}"),
            InlineKeyboardButton("✏️ Rename", callback_data=f"rename_wallet:{wallet_address}")
        ],
        [InlineKeyboardButton("⏹️ Stop Watching", callback_data=f"confirm_stop:{wallet_address}")]
    ]

    return message, InlineKeyboardMarkup(keyboard)

async def refresh_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh the portfolio message with a cooldown."""
    query = update.callback_query
    wallet_address = query.data.split(":")[1]
    user_id = query.from_user.id
    current_time = time.time()
    
    if current_time - last_refresh_time.get((user_id, wallet_address), 0) < 10:
        await query.answer("⏳ Please wait 10 seconds before refreshing again!", show_alert=True)
        return
    
    last_refresh_time[(user_id, wallet_address)] = current_time
    await query.answer("Refreshing...")
    
    chat_id = query.message.chat_id
    new_message, new_markup = await generate_profile_message(chat_id, wallet_address, is_refresh=True)
    await query.edit_message_text(
        new_message,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=new_markup
    )

async def watch_wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the 'Watch Wallet' button click."""
    query = update.callback_query
    wallet_address = query.data.split(":")[1]
    chat_id = query.message.chat_id

    wallets = get_wallets(chat_id)
    if any(wallet == wallet_address for wallet, _ in wallets):
        await query.answer("✅ Already watching this wallet!", show_alert=True)
    else:
        add_wallet(chat_id, wallet_address)
        task = asyncio.create_task(watch_wallet(wallet_address, chat_id, context.bot))
        if chat_id not in USER_WATCH_TASKS:
            USER_WATCH_TASKS[chat_id] = {}
        USER_WATCH_TASKS[chat_id][wallet_address] = task
        display_name = get_wallet_display(chat_id, wallet_address)
        await query.answer(f"✅ Now watching {display_name}.", show_alert=True)

async def watch_wallet(wallet_address: str, chat_id: int, bot):
    """Monitor the wallet for new transactions and send updates."""
    start_timestamp = int(datetime.now(timezone.utc).timestamp())
    url = (
        f"https://api.bscscan.com/api?module=account&action=tokentx&address={wallet_address}"
        f"&startblock=0&endblock=99999999&sort=desc&apikey={BSCSCAN_API_KEY}"
    )
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data["status"] == "1" and "result" in data:
            for tx in data["result"]:
                if int(tx["timeStamp"]) <= start_timestamp:
                    add_seen_tx(chat_id, wallet_address, tx["hash"])
    
    while True:
        wallets = get_wallets(chat_id)
        if not any(wallet == wallet_address for wallet, _ in wallets):
            logger.info(f"Stopped watching wallet {wallet_address} for chat_id {chat_id}")
            break
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data["status"] == "1" and "result" in data:
                seen_txs = get_seen_txs(chat_id, wallet_address)
                for tx in data["result"]:
                    tx_timestamp = int(tx["timeStamp"])
                    tx_hash = tx["hash"]
                    if tx_timestamp > start_timestamp and tx_hash not in seen_txs:
                        add_seen_tx(chat_id, wallet_address, tx_hash)
                        tx_type = "🟢 Buy" if tx["to"].lower() == wallet_address.lower() else "🔴 Sell"
                        token_symbol = tx["tokenSymbol"]
                        token_decimal = int(tx["tokenDecimal"])
                        amount = int(tx["value"]) / (10 ** token_decimal)
                        contract_address = tx["contractAddress"]

                        display_name = get_wallet_display(chat_id, wallet_address)
                        message = (
                            f"🚨 *New {tx_type} Transaction Detected for {display_name}!*\n\n"
                            f"• Token: {token_symbol}\n"
                            f"• Contract: {contract_address}\n"
                            f"• Amount: {amount:,.2f}\n"
                            f"🔗 [Buy on Meastro](https://t.me/maestro?start=buy_{contract_address}) | "
                            f"[Scan with TTF](https://t.me/ttfbotbot?start=scan_{contract_address}) | "
                            f"[Scan with Otto](https://t.me/OttoSimBot?start=scan_{contract_address})\n"
                        )

                        await bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode="Markdown",
                            disable_web_page_preview=True
                        )
        else:
            logger.warning(f"Failed to fetch transactions for {wallet_address}: HTTP {response.status_code}")

        await asyncio.sleep(30)

async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start watching a wallet for new transactions."""
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a wallet address.\nExample: `/watch 0x123...`",
            parse_mode="Markdown"
        )
        return

    wallet_address = context.args[0]
    chat_id = update.effective_chat.id
    wallets = get_wallets(chat_id)
    if any(wallet == wallet_address for wallet, _ in wallets):
        display_name = get_wallet_display(chat_id, wallet_address)
        await update.message.reply_text(
            f"Wallet {display_name} is already being watched.",
            parse_mode="Markdown"
        )
    else:
        add_wallet(chat_id, wallet_address)
        task = asyncio.create_task(watch_wallet(wallet_address, chat_id, context.bot))
        if chat_id not in USER_WATCH_TASKS:
            USER_WATCH_TASKS[chat_id] = {}
        USER_WATCH_TASKS[chat_id][wallet_address] = task
        display_name = get_wallet_display(chat_id, wallet_address)
        await update.message.reply_text(
            f"✅ Started watching wallet: {display_name}.",
            parse_mode="Markdown"
        )

async def watched(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all wallets currently being watched with custom names."""
    chat_id = update.effective_chat.id
    wallets = get_wallets(chat_id)
    if not wallets:
        await update.message.reply_text("No wallets are currently being watched.", parse_mode="Markdown")
    else:
        message = "👀 *Watched Wallets:*\n"
        for idx, (wallet, _) in enumerate(wallets, 1):
            display_name = get_wallet_display(chat_id, wallet)
            message += f"{idx}. {display_name}\n"
        await update.message.reply_text(message, parse_mode="Markdown")

async def stopwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop watching a wallet with confirmation."""
    chat_id = update.effective_chat.id
    wallets = get_wallets(chat_id)
    if not context.args:
        if not wallets:
            await update.message.reply_text("No wallets are currently being watched.", parse_mode="Markdown")
            return
        keyboard = [
            [InlineKeyboardButton(text=get_wallet_display(chat_id, wallet), callback_data=f"confirm_stop:{wallet}")]
            for wallet, _ in wallets
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select a wallet to stop watching:", reply_markup=reply_markup)
    else:
        wallet_address = context.args[0]
        display_name = get_wallet_display(chat_id, wallet_address)
        keyboard = [
            [
                InlineKeyboardButton(text="✅ Yes", callback_data=f"stop_yes:{wallet_address}"),
                InlineKeyboardButton(text="❌ No", callback_data=f"stop_no:{wallet_address}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Do you want to stop watching {display_name}?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def stop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries for stopping a wallet."""
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    wallet_address = data.split(":", 1)[1]
    display_name = get_wallet_display(chat_id, wallet_address)

    if data.startswith("confirm_stop:"):
        keyboard = [
            [
                InlineKeyboardButton(text="✅ Yes", callback_data=f"stop_yes:{wallet_address}"),
                InlineKeyboardButton(text="❌ No", callback_data=f"stop_no:{wallet_address}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Do you want to stop watching {display_name}?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

    elif data.startswith("stop_yes:"):
        remove_wallet(chat_id, wallet_address)
        if chat_id in USER_WATCH_TASKS and wallet_address in USER_WATCH_TASKS[chat_id]:
            task = USER_WATCH_TASKS[chat_id].pop(wallet_address)
            task.cancel()
        await query.edit_message_text(
            f"⏹️ Stopped watching {display_name}.",
            parse_mode="Markdown"
        )

    elif data.startswith("stop_no:"):
        await query.edit_message_text(
            f"✅ Continuing to watch {display_name}.",
            parse_mode="Markdown"
        )

# ========== Wallet Detection Handler ==========
async def detect_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle raw wallet address messages and offer quick actions."""
    wallet_address = update.message.text.strip()
    chat_id = update.effective_chat.id
    display_name = get_wallet_display(chat_id, wallet_address)
    keyboard = [
        [
            InlineKeyboardButton("📊 View Portfolio", callback_data=f"quick_view:{wallet_address}"),
            InlineKeyboardButton("👀 Watch Wallet", callback_data=f"quick_watch:{wallet_address}")
        ]
    ]
    await update.message.reply_text(
        f"Detected BSC wallet: {display_name}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== Quick Action Callbacks ==========
async def quick_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quick portfolio view from detected wallet."""
    query = update.callback_query
    wallet_address = query.data.split(":")[1]
    chat_id = query.message.chat_id
    message_text, reply_markup = await generate_profile_message(chat_id, wallet_address, is_refresh=False)
    await query.message.reply_text(
        message_text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )
    await query.answer()

async def quick_watch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quick watch action from detected wallet."""
    query = update.callback_query
    wallet_address = query.data.split(":")[1]
    chat_id = query.message.chat_id
    wallets = get_wallets(chat_id)
    display_name = get_wallet_display(chat_id, wallet_address)
    if any(wallet == wallet_address for wallet, _ in wallets):
        await query.answer(f"✅ Already watching {display_name}!", show_alert=True)
    else:
        add_wallet(chat_id, wallet_address)
        task = asyncio.create_task(watch_wallet(wallet_address, chat_id, context.bot))
        if chat_id not in USER_WATCH_TASKS:
            USER_WATCH_TASKS[chat_id] = {}
        USER_WATCH_TASKS[chat_id][wallet_address] = task
        await query.answer(f"✅ Now watching {display_name}.", show_alert=True)

# ========== Renaming Feature ==========
async def rename_wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate the wallet renaming process."""
    query = update.callback_query
    wallet_address = query.data.split(":")[1]
    
    context.user_data['renaming_wallet'] = wallet_address
    await query.message.reply_text("Please enter a new name for this wallet:")
    await query.answer()

async def save_wallet_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the custom wallet name provided by the user."""
    chat_id = update.effective_chat.id
    wallet_address = context.user_data.get('renaming_wallet')
    if wallet_address:
        custom_name = update.message.text.strip()
        update_wallet_name(chat_id, wallet_address, custom_name)
        del context.user_data['renaming_wallet']
        await update.message.reply_text(f"✅ Wallet renamed to: {custom_name}")

# ========== Main Application Setup ==========
def main():
    """Set up and run the Telegram bot application."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("watch", watch_command))
    application.add_handler(CommandHandler("watched", watched))
    application.add_handler(CommandHandler("stopwatch", stopwatch))
    
    # Callback Query Handlers
    application.add_handler(CallbackQueryHandler(refresh_profile, pattern="^refresh_profile:"))
    application.add_handler(CallbackQueryHandler(watch_wallet_callback, pattern="^watch_wallet:"))
    application.add_handler(CallbackQueryHandler(stop_callback, pattern="^confirm_stop:"))
    application.add_handler(CallbackQueryHandler(stop_callback, pattern="^stop_yes:"))
    application.add_handler(CallbackQueryHandler(stop_callback, pattern="^stop_no:"))
    application.add_handler(CallbackQueryHandler(rename_wallet_callback, pattern="^rename_wallet:"))
    application.add_handler(CallbackQueryHandler(quick_view_callback, pattern="^quick_view:"))
    application.add_handler(CallbackQueryHandler(quick_watch_callback, pattern="^quick_watch:"))
    
    # Message Handlers
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'^0x[a-fA-F0-9]{40}$'),
        detect_wallet
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        save_wallet_name
    ))
    
    # Restart watching all wallets from the database
    try:
        conn = sqlite3.connect("/data/bot_data.db")
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT chat_id FROM user_wallets")
        chat_ids = cursor.fetchall()
        for (chat_id,) in chat_ids:
            wallets = get_wallets(chat_id)
            if chat_id not in USER_WATCH_TASKS:
                USER_WATCH_TASKS[chat_id] = {}
            for wallet_address, _ in wallets:
                if wallet_address not in USER_WATCH_TASKS[chat_id]:
                    task = asyncio.create_task(watch_wallet(wallet_address, chat_id, application.bot))
                    USER_WATCH_TASKS[chat_id][wallet_address] = task
                    display_name = get_wallet_display(chat_id, wallet_address)
                    logger.info(f"Restarted watching wallet {display_name} for chat_id {chat_id}")
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"Failed to restart wallet watching: {e}")

    application.run_polling()

if __name__ == '__main__':
    main()
