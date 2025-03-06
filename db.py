import sqlite3
import logging

# Configure logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database file path (adjusted for Railway volume)
DB_FILE = "/data/bot_data.db"

def get_connection():
    """Create a connection to the SQLite database."""
    try:
        return sqlite3.connect(DB_FILE)
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def init_db():
    """Initialize the database with required tables."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        # Table for watched wallets and their custom names
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_wallets (
                chat_id INTEGER,
                wallet_address TEXT,
                custom_name TEXT,
                PRIMARY KEY (chat_id, wallet_address)
            )
        ''')
        # Table for seen transactions to avoid duplicates
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS seen_transactions (
                chat_id INTEGER,
                wallet_address TEXT,
                tx_hash TEXT,
                PRIMARY KEY (chat_id, wallet_address, tx_hash)
            )
        ''')
        conn.commit()
        logger.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        conn.close()

def add_wallet(chat_id, wallet_address, custom_name=None):
    """Add or update a wallet to watch for a user."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_wallets (chat_id, wallet_address, custom_name)
            VALUES (?, ?, ?)
        ''', (chat_id, wallet_address, custom_name))
        conn.commit()
        logger.info(f"Added wallet {wallet_address} for chat_id {chat_id}")
    except sqlite3.Error as e:
        logger.error(f"Failed to add wallet: {e}")
        raise
    finally:
        conn.close()

def remove_wallet(chat_id, wallet_address):
    """Remove a wallet from the watch list."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM user_wallets WHERE chat_id = ? AND wallet_address = ?
        ''', (chat_id, wallet_address))
        conn.commit()
        logger.info(f"Removed wallet {wallet_address} for chat_id {chat_id}")
    except sqlite3.Error as e:
        logger.error(f"Failed to remove wallet: {e}")
        raise
    finally:
        conn.close()

def get_wallets(chat_id):
    """Retrieve all wallets being watched by a user."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT wallet_address, custom_name FROM user_wallets WHERE chat_id = ?
        ''', (chat_id,))
        wallets = cursor.fetchall()
        return wallets  # Returns list of tuples (wallet_address, custom_name)
    except sqlite3.Error as e:
        logger.error(f"Failed to get wallets for chat_id {chat_id}: {e}")
        return []
    finally:
        conn.close()

def add_seen_tx(chat_id, wallet_address, tx_hash):
    """Add a seen transaction to avoid duplicate notifications."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO seen_transactions (chat_id, wallet_address, tx_hash)
            VALUES (?, ?, ?)
        ''', (chat_id, wallet_address, tx_hash))
        conn.commit()
        logger.debug(f"Added seen transaction {tx_hash} for wallet {wallet_address}, chat_id {chat_id}")
    except sqlite3.Error as e:
        logger.error(f"Failed to add seen transaction: {e}")
        raise
    finally:
        conn.close()

def get_seen_txs(chat_id, wallet_address):
    """Retrieve all seen transaction hashes for a wallet."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tx_hash FROM seen_transactions WHERE chat_id = ? AND wallet_address = ?
        ''', (chat_id, wallet_address))
        txs = cursor.fetchall()
        return set(tx[0] for tx in txs)  # Convert to set for efficient lookup
    except sqlite3.Error as e:
        logger.error(f"Failed to get seen transactions for wallet {wallet_address}, chat_id {chat_id}: {e}")
        return set()
    finally:
        conn.close()

def update_wallet_name(chat_id, wallet_address, custom_name):
    """Update the custom name for a wallet."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE user_wallets SET custom_name = ? WHERE chat_id = ? AND wallet_address = ?
        ''', (custom_name, chat_id, wallet_address))
        conn.commit()
        logger.info(f"Updated name for wallet {wallet_address} to '{custom_name}' for chat_id {chat_id}")
    except sqlite3.Error as e:
        logger.error(f"Failed to update wallet name: {e}")
        raise
    finally:
        conn.close()
