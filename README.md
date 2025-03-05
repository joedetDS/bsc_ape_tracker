# BSCApeTracker

BSCApeTracker is a Telegram bot that allows users to monitor their Binance Smart Chain (BSC) wallets. It provides real-time tracking of wallet balances, transactions, and token holdings. Users can watch specific wallets, receive alerts on new transactions, and refresh their portfolio insights with a single click.

## Features 🚀
- 📊 View wallet portfolio with BNB and token balances
- 👀 Watch wallets to receive real-time transaction alerts
- 🔄 Refresh wallet data on demand
- 📈 Track last buy and sell transactions
- 📌 User-friendly Telegram commands for ease of use

## Commands 📌

**General Commands:**
- `/start` - Start the bot
- `/help` - Show available commands

**Wallet Tracking Commands:**
- `/profile <wallet_address>` - View wallet portfolio
- `/watch <wallet_address>` - Start watching a wallet
- `/watched` - List watched wallets
- `/stopwatch <wallet_address>` - Stop watching a wallet

## Installation & Setup ⚙️

### Prerequisites:
- Python 3.8+
- A Telegram bot token (from @BotFather)
- BSCScan API Key

### Clone the Repository
```sh
$ git clone https://github.com/joedetDS/bsc_ape_tracker.git
$ cd bsc_ape_tracker
```

### Install Dependencies
```sh
$ pip install -r requirements.txt
```

### Configure Environment Variables
Create a `.env` file and add:
```sh
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
BSCSCAN_API_KEY=your_bscscan_api_key
```

### Run the Bot
```sh
$ python bot.py
```

## Deployment 🚀
This bot can be deployed on platforms like Heroku, Render, or a VPS.

For Heroku, create a `Procfile`:
```sh
worker: python bot.py
```
Then deploy using:
```sh
$ git add .
$ git commit -m "Deploying bot"
$ git push heroku main
```

## Files in the Repository 📂
- `bot.py` - Main bot script
- `config.py` - Configuration settings
- `utils.py` - Utility functions for wallet tracking and token analysis
- `requirements.txt` - Dependencies list
- `Procfile.txt` - Deployment file for Heroku

## Contributing 🤝
Feel free to fork this repository and submit pull requests to improve the bot. Open an issue for bug reports or feature requests.

## License 📜
This project is open-source under the MIT License.

