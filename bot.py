import os
import asyncio
import requests
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
from utils import (
    get_bnb_balance,
    get_token_balances,
    get_last_transactions,
    get_bnb_price,
    get_token_market_cap
)
from config import TELEGRAM_BOT_TOKEN, BSCSCAN_API_KEY

# Load environment variables
load_dotenv()

WELCOME_MESSAGE = """
🚀 *Welcome to BSC Portfolio Tracker!* 🚀

Commands:
/profile <wallet_address> - View your portfolio
/watch <wallet_address> - Start monitoring a wallet
/watched - List currently watched wallets
/stopwatch [wallet_address] - Stop watching a wallet (if not provided, list watched wallets)
"""

# Global dictionary to store watching tasks; keys are wallet addresses
WATCH_TASKS = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message."""
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /profile command."""
    if not context.args:
        await update.message.reply_text("❌ Please provide a wallet address.\nExample: `/profile 0x123...`", parse_mode="Markdown")
        return

    wallet_address = context.args[0]
    
    # Get native BNB balance and current price
    native_bnb = get_bnb_balance(wallet_address)
    bnb_price = get_bnb_price()
    bnb_usd_value = float(native_bnb) * float(bnb_price)
    
    # Get token balances and filter only tokens with positive balance (excluding BNB)
    tokens = get_token_balances(wallet_address)
    tokens = [token for token in tokens if token["balance"] > 0 and token["symbol"].upper() != "BNB"]
    # Limit to top 10 tokens (if there are more than 10)
    if len(tokens) > 10:
        tokens = tokens[:10]
    # Insert native BNB as the first entry
    tokens.insert(0, {"symbol": "BNB", "balance": native_bnb})
    
    message = f"📊 *Portfolio for {wallet_address}*\n\n"
    message += "⛓️ *BNB Balance:*\n"
    message += f"💰 Total: {native_bnb:,.7f} BNB (~${bnb_usd_value:,.2f} USD)\n\n"
    message += f"🔢 *Tokens Held:* {len(tokens):,}\n\n"
    for token in tokens:
        message += f"• {token['symbol']}: {token['balance']:,.2f}\n"
    
    # Append details for last buy and sell transactions
    last_transactions = get_last_transactions(wallet_address)
    if last_transactions["buy"]:
        buy_time = datetime.fromtimestamp(last_transactions["buy"]["timestamp"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        message += "\n🟢 *Last Buy:*\n"
        message += f"• Token: {last_transactions['buy']['symbol']}\n"
        message += f"• Amount: {last_transactions['buy']['amount']:,.2f}\n"
        message += f"• Timestamp: {buy_time}\n"
        message += f"• [View Transaction](https://bscscan.com/tx/{last_transactions['buy']['tx_hash']})\n"
    
    if last_transactions["sell"]:
        sell_time = datetime.fromtimestamp(last_transactions["sell"]["timestamp"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        message += "\n🔴 *Last Sell:*\n"
        message += f"• Token: {last_transactions['sell']['symbol']}\n"
        message += f"• Amount: {last_transactions['sell']['amount']:,.2f}\n"
        message += f"• Timestamp: {sell_time}\n"
        message += f"• [View Transaction](https://bscscan.com/tx/{last_transactions['sell']['tx_hash']})\n"
    
    await update.message.reply_text(message, parse_mode="Markdown", disable_web_page_preview=True)

async def watch_wallet(wallet_address: str, chat_id: int, bot):
    """Background task: continuously poll for new transactions for a given wallet."""
    start_timestamp = int(datetime.now(timezone.utc).timestamp())
    seen_txs = set()
    url = (f"https://api.bscscan.com/api?module=account&action=tokentx&address={wallet_address}"
           f"&startblock=0&endblock=99999999&sort=desc&apikey={BSCSCAN_API_KEY}")
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data["status"] == "1" and "result" in data:
            for tx in data["result"]:
                if int(tx["timeStamp"]) <= start_timestamp:
                    seen_txs.add(tx["hash"])
    
    while True:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data["status"] == "1" and "result" in data:
                for tx in data["result"]:
                    tx_timestamp = int(tx["timeStamp"])
                    tx_hash = tx["hash"]
                    if tx_timestamp > start_timestamp and tx_hash not in seen_txs:
                        seen_txs.add(tx_hash)
                        tx_type = "Buy" if tx["to"].lower() == wallet_address.lower() else "Sell"
                        token_symbol = tx["tokenSymbol"]
                        token_decimal = int(tx["tokenDecimal"])
                        amount = int(tx["value"]) / (10 ** token_decimal)
                        message = f"🚨 *New {tx_type} Transaction Detected!*\n"
                        message += f"• Token: {token_symbol}\n"
                        message += f"• Contract: {tx['contractAddress']}\n"
                        message += f"• Amount: {amount:,.2f}\n"
                        message += f"• [Buy on Meastro](https://t.me/maestro?start=buy_{tx['contractAddress']}) | "
                        message += f"[Scan](https://t.me/ttfbotbot?start=scan_{tx['contractAddress']})\n"
                        await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown", disable_web_page_preview=True)
        await asyncio.sleep(30)

async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start watching a wallet for new transactions."""
    if not context.args:
        await update.message.reply_text("❌ Please provide a wallet address.\nExample: `/watch 0x123...`", parse_mode="Markdown")
        return

    wallet_address = context.args[0]
    chat_id = update.effective_chat.id
    if wallet_address in WATCH_TASKS:
        await update.message.reply_text(f"Wallet {wallet_address} is already being watched.", parse_mode="Markdown")
    else:
        task = asyncio.create_task(watch_wallet(wallet_address, chat_id, context.bot))
        WATCH_TASKS[wallet_address] = task
        await update.message.reply_text(f"Started watching wallet: {wallet_address}.", parse_mode="Markdown")

async def watched(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all wallets that are currently being watched."""
    if not WATCH_TASKS:
        await update.message.reply_text("No wallets are currently being watched.", parse_mode="Markdown")
    else:
        wallets = "\n".join(WATCH_TASKS.keys())
        await update.message.reply_text(f"Watched wallets:\n{wallets}", parse_mode="Markdown")

# --- Interactive Stopwatch Implementation ---
async def stopwatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Stop watching a wallet.
    If no wallet is provided, list all watched wallets as inline buttons.
    If a wallet is provided, show a confirmation inline keyboard.
    """
    if not context.args:
        # No argument provided: list watched wallets if any.
        if not WATCH_TASKS:
            await update.message.reply_text("No wallets are currently being watched.", parse_mode="Markdown")
            return
        keyboard = [
            [InlineKeyboardButton(text=wa, callback_data=f"confirm_stop:{wa}")]
            for wa in WATCH_TASKS.keys()
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select a wallet to stop watching:", reply_markup=reply_markup)
    else:
        wallet_address = context.args[0]
        keyboard = [
            [InlineKeyboardButton(text="Yes", callback_data=f"stop_yes:{wallet_address}"),
             InlineKeyboardButton(text="No", callback_data=f"stop_no:{wallet_address}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"Do you want to stop watching wallet {wallet_address}?", reply_markup=reply_markup)

async def stop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries for stopping a wallet."""
    query = update.callback_query
    await query.answer()
    data = query.data
    # data format: "confirm_stop:<wallet_address>" or "stop_yes:<wallet_address>" or "stop_no:<wallet_address>"
    if data.startswith("confirm_stop:"):
        wallet_address = data.split(":", 1)[1]
        # Show confirmation inline keyboard
        keyboard = [
            [InlineKeyboardButton(text="Yes", callback_data=f"stop_yes:{wallet_address}"),
             InlineKeyboardButton(text="No", callback_data=f"stop_no:{wallet_address}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Do you want to stop watching wallet {wallet_address}?", reply_markup=reply_markup)
    elif data.startswith("stop_yes:"):
        wallet_address = data.split(":", 1)[1]
        if wallet_address in WATCH_TASKS:
            task = WATCH_TASKS.pop(wallet_address)
            task.cancel()
            await query.edit_message_text(f"Stopped watching wallet: {wallet_address}.")
        else:
            await query.edit_message_text(f"Wallet {wallet_address} was not being watched.")
    elif data.startswith("stop_no:"):
        wallet_address = data.split(":", 1)[1]
        await query.edit_message_text(f"Continuing to watch wallet: {wallet_address}.")

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("watch", watch_command))
    application.add_handler(CommandHandler("watched", watched))
    application.add_handler(CommandHandler("stopwatch", stopwatch))
    application.add_handler(CallbackQueryHandler(stop_callback))
    
    application.run_polling()

if __name__ == '__main__':
    main()
