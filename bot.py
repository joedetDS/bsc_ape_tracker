import os
import time
import asyncio
import requests
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from utils import (
    get_bnb_balance,
    get_token_balances,
    get_last_transactions,
    get_bnb_price
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CallbackContext
from config import TELEGRAM_BOT_TOKEN, BSCSCAN_API_KEY
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
\n
🔹 <b>Wallet Tracking Commands:</b>
/profile &lt;wallet_address&gt; - View wallet portfolio
/watch &lt;wallet_address&gt; - Start watching a wallet
/watched - List watched wallets
/stopwatch &lt;wallet_address&gt; - Stop watching a wallet
"""

# Store tasks and seen transactions per user
USER_WATCH_TASKS = {}  # Format: {chat_id: {wallet_address: task}}
USER_SEEN_TXS = {}  # Format: {chat_id: {wallet_address: set(tx_hashes)}}

last_refresh_time = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_MESSAGE, parse_mode="HTML", disable_web_page_preview=True)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Please provide a wallet address.\nExample: `/profile 0x123...`", parse_mode="Markdown")
        return

    wallet_address = context.args[0]
    message_text, reply_markup = await generate_profile_message(wallet_address, is_refresh=False)
    await update.message.reply_text(message_text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=reply_markup)

async def generate_profile_message(wallet_address, is_refresh=False):
    native_bnb = get_bnb_balance(wallet_address)
    bnb_price = get_bnb_price()
    bnb_usd_value = float(native_bnb) * float(bnb_price)
    
    all_tokens = get_token_balances(wallet_address)
    filtered_tokens = [token for token in all_tokens if token["balance"] > 0 and token["symbol"].upper() != "BNB"]
    display_tokens = filtered_tokens[:10] if len(filtered_tokens) > 10 else filtered_tokens
    
    message = f"📊 *Portfolio for {wallet_address}*\n\n"
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
            InlineKeyboardButton("⏹️ Stop Watching", callback_data=f"confirm_stop:{wallet_address}")
        ]
    ]

    return message, InlineKeyboardMarkup(keyboard)

async def refresh_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    wallet_address = query.data.split(":")[1]
    user_id = query.from_user.id
    current_time = time.time()
    
    if current_time - last_refresh_time.get((user_id, wallet_address), 0) < 10:
        await query.answer("⏳ Please wait 10 seconds before refreshing again!", show_alert=True)
        return
    
    last_refresh_time[(user_id, wallet_address)] = current_time
    await query.answer("Refreshing...")
    
    new_message, new_markup = await generate_profile_message(wallet_address, is_refresh=True)
    await query.edit_message_text(new_message, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=new_markup)

async def watch_wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the 'Watch Wallet' button click."""
    query = update.callback_query
    wallet_address = query.data.split(":")[1]
    chat_id = query.message.chat_id

    if chat_id in USER_WATCH_TASKS and wallet_address in USER_WATCH_TASKS[chat_id]:
        await query.answer("✅ Already watching this wallet!", show_alert=True)
    else:
        task = asyncio.create_task(watch_wallet(wallet_address, chat_id, context.bot))
        if chat_id not in USER_WATCH_TASKS:
            USER_WATCH_TASKS[chat_id] = {}
        USER_WATCH_TASKS[chat_id][wallet_address] = task
        if chat_id not in USER_SEEN_TXS:
            USER_SEEN_TXS[chat_id] = {}
        USER_SEEN_TXS[chat_id][wallet_address] = set()
        await query.answer(f"✅ Now watching {wallet_address}.", show_alert=True)

async def watch_wallet(wallet_address: str, chat_id: int, bot):
    """Monitor the wallet for new transactions and send updates."""
    start_timestamp = int(datetime.now(timezone.utc).timestamp())
    url = (f"https://api.bscscan.com/api?module=account&action=tokentx&address={wallet_address}"
           f"&startblock=0&endblock=99999999&sort=desc&apikey={BSCSCAN_API_KEY}")
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data["status"] == "1" and "result" in data:
            for tx in data["result"]:
                if int(tx["timeStamp"]) <= start_timestamp:
                    USER_SEEN_TXS[chat_id][wallet_address].add(tx["hash"])
    
    while chat_id in USER_WATCH_TASKS and wallet_address in USER_WATCH_TASKS[chat_id]:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data["status"] == "1" and "result" in data:
                for tx in data["result"]:
                    tx_timestamp = int(tx["timeStamp"])
                    tx_hash = tx["hash"]
                    if tx_timestamp > start_timestamp and tx_hash not in USER_SEEN_TXS[chat_id][wallet_address]:
                        USER_SEEN_TXS[chat_id][wallet_address].add(tx_hash)
                        tx_type = "🟢 Buy" if tx["to"].lower() == wallet_address.lower() else "🔴 Sell"
                        token_symbol = tx["tokenSymbol"]
                        token_decimal = int(tx["tokenDecimal"])
                        amount = int(tx["value"]) / (10 ** token_decimal)
                        contract_address = tx["contractAddress"]

                        message = (
                            f"🚨 *New {tx_type} Transaction Detected!*\n\n"
                            f"• Token: {token_symbol}\n"
                            f"• Contract: {contract_address}\n"
                            f"• Amount: {amount:,.2f}\n"
                            f"🔗 [Buy on Meastro](https://t.me/maestro?start=buy_{contract_address}) | "
                            f"[Scan](https://t.me/ttfbotbot?start=scan_{contract_address})\n"
                        )

                        await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown", disable_web_page_preview=True)

        await asyncio.sleep(30)  # Poll every 30 seconds

async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start watching a wallet for new transactions."""
    if not context.args:
        await update.message.reply_text("❌ Please provide a wallet address.\nExample: `/watch 0x123...`", parse_mode="Markdown")
        return

    wallet_address = context.args[0]
    chat_id = update.effective_chat.id
    if chat_id in USER_WATCH_TASKS and wallet_address in USER_WATCH_TASKS[chat_id]:
        await update.message.reply_text(f"Wallet {wallet_address} is already being watched.", parse_mode="Markdown")
    else:
        task = asyncio.create_task(watch_wallet(wallet_address, chat_id, context.bot))
        if chat_id not in USER_WATCH_TASKS:
            USER_WATCH_TASKS[chat_id] = {}
        USER_WATCH_TASKS[chat_id][wallet_address] = task
        if chat_id not in USER_SEEN_TXS:
            USER_SEEN_TXS[chat_id] = {}
        USER_SEEN_TXS[chat_id][wallet_address] = set()
        await update.message.reply_text(f"✅ Started watching wallet: {wallet_address}.", parse_mode="Markdown")

async def watched(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all wallets that are currently being watched."""
    chat_id = update.effective_chat.id
    if chat_id not in USER_WATCH_TASKS or not USER_WATCH_TASKS[chat_id]:
        await update.message.reply_text("No wallets are currently being watched.", parse_mode="Markdown")
    else:
        wallets = "\n".join(USER_WATCH_TASKS[chat_id].keys())
        await update.message.reply_text(f"👀 *Watched Wallets:*\n{wallets}", parse_mode="Markdown")

async def stopwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Stop watching a wallet.
    If no wallet is provided, list all watched wallets as inline buttons.
    If a wallet is provided, show a confirmation inline keyboard.
    """
    chat_id = update.effective_chat.id
    if not context.args:
        if chat_id not in USER_WATCH_TASKS or not USER_WATCH_TASKS[chat_id]:
            await update.message.reply_text("No wallets are currently being watched.", parse_mode="Markdown")
            return
        keyboard = [
            [InlineKeyboardButton(text=wa, callback_data=f"confirm_stop:{wa}")]
            for wa in USER_WATCH_TASKS[chat_id].keys()
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select a wallet to stop watching:", reply_markup=reply_markup)
    else:
        wallet_address = context.args[0]
        keyboard = [
            [InlineKeyboardButton(text="✅ Yes", callback_data=f"stop_yes:{wallet_address}"),
             InlineKeyboardButton(text="❌ No", callback_data=f"stop_no:{wallet_address}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"Do you want to stop watching wallet {wallet_address}?", reply_markup=reply_markup)

async def stop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries for stopping a wallet."""
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    if data.startswith("confirm_stop:"):
        wallet_address = data.split(":", 1)[1]
        keyboard = [
            [InlineKeyboardButton(text="✅ Yes", callback_data=f"stop_yes:{wallet_address}"),
             InlineKeyboardButton(text="❌ No", callback_data=f"stop_no:{wallet_address}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Do you want to stop watching wallet {wallet_address}?", reply_markup=reply_markup)

    elif data.startswith("stop_yes:"):
        wallet_address = data.split(":", 1)[1]
        if chat_id in USER_WATCH_TASKS and wallet_address in USER_WATCH_TASKS[chat_id]:
            task = USER_WATCH_TASKS[chat_id].pop(wallet_address)
            task.cancel()
            await query.edit_message_text(f"⏹️ Stopped watching wallet: {wallet_address}.")
        else:
            await query.edit_message_text(f"⚠️ Wallet {wallet_address} was not being watched.")

    elif data.startswith("stop_no:"):
        wallet_address = data.split(":", 1)[1]
        await query.edit_message_text(f"✅ Continuing to watch wallet: {wallet_address}.")

# Main
def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("watch", watch_command))
    application.add_handler(CallbackQueryHandler(refresh_profile, pattern="^refresh_profile:"))
    application.add_handler(CallbackQueryHandler(watch_wallet_callback, pattern="^watch_wallet:"))
    application.add_handler(CommandHandler("watched", watched))
    application.add_handler(CommandHandler("stopwatch", stopwatch))
    application.add_handler(CallbackQueryHandler(stop_callback, pattern="^confirm_stop:"))
    application.add_handler(CallbackQueryHandler(stop_callback, pattern="^stop_yes:"))
    application.add_handler(CallbackQueryHandler(stop_callback, pattern="^stop_no:"))

    application.run_polling()

if __name__ == '__main__':
    main()
