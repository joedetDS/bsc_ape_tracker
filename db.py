import os
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
        # Ensure the directory exists
        db_dir = os.path.dirname(DB_FILE)
        if db_dir and not os.path.exists(db_dir):  # Check if directory path is non-empty
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")
        conn = sqlite3.connect(DB_FILE)
        logger.debug(f"Connected to database at {DB_FILE}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to database {DB_FILE}: {e}")
        raise
    except OSError as e:
        logger.error(f"Failed to create directory {db_dir}: {e}")
        raise

def init_db():
    """Initialize the database with required tables."""
    conn = None  # Initialize conn to None to avoid UnboundLocalError
    try:
        conn = get_connection()  # This will create the directory if needed
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
        logger.info("Database initialized successfully with tables 'user_wallets' and 'seen_transactions'")
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during database initialization: {e}")
        raise
    finally:
        if conn is not None:  # Only close if conn was successfully created
            conn.close()
            logger.debug("Database connection closed after initialization")

def add_wallet(chat_id, wallet_address, custom_name=None):
    """Add or update a wallet to watch for a user."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_wallets (chat_id, wallet_address, custom_name)
            VALUES (?, ?, ?)
        ''', (chat_id, wallet_address, custom_name))
        conn.commit()
        logger.info(f"Added/Updated wallet {wallet_address} for chat_id {chat_id} with custom_name={custom_name}")
    except sqlite3.Error as e:
        logger.error(f"Failed to add wallet {wallet_address} for chat_id {chat_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error adding wallet {wallet_address}: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()
            logger.debug("Database connection closed after adding wallet")

def remove_wallet(chat_id, wallet_address):
    """Remove a wallet from the watch list."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM user_wallets WHERE chat_id = ? AND wallet_address = ?
        ''', (chat_id, wallet_address))
        conn.commit()
        logger.info(f"Removed wallet {wallet_address} for chat_id {chat_id}")
    except sqlite3.Error as e:
        logger.error(f"Failed to remove wallet {wallet_address} for chat_id {chat_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error removing wallet {wallet_address}: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()
            logger.debug("Database connection closed after removing wallet")

def get_wallets(chat_id):
    """Retrieve all wallets being watched by a user."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT wallet_address, custom_name FROM user_wallets WHERE chat_id = ?
        ''', (chat_id,))
        wallets = cursor.fetchall()
        logger.debug(f"Retrieved {len(wallets)} wallets for chat_id {chat_id}")
        return wallets  # Returns list of tuples (wallet_address, custom_name)
    except sqlite3.Error as e:
        logger.error(f"Failed to get wallets for chat_id {chat_id}: {e}")
        return []  # Return empty list on failure to keep bot running
    except Exception as e:
        logger.error(f"Unexpected error retrieving wallets for chat_id {chat_id}: {e}")
        return []
    finally:
        if conn is not None:
            conn.close()
            logger.debug("Database connection closed after getting wallets")

def add_seen_tx(chat_id, wallet_address, tx_hash):
    """Add a seen transaction to avoid duplicate notifications."""
    conn = None
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
        logger.error(f"Failed to add seen transaction {tx_hash} for wallet {wallet_address}, chat_id {chat_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error adding transaction {tx_hash}: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()
            logger.debug("Database connection closed after adding seen transaction")

def get_seen_txs(chat_id, wallet_address):
    """Retrieve all seen transaction hashes for a wallet."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT tx_hash FROM seen_transactions WHERE chat_id = ? AND wallet_address = ?
        ''', (chat_id, wallet_address))
        txs = cursor.fetchall()
        logger.debug(f"Retrieved {len(txs)} seen transactions for wallet {wallet_address}, chat_id {chat_id}")
        return set(tx[0] for tx in txs)  # Convert to set for efficient lookup
    except sqlite3.Error as e:
        logger.error(f"Failed to get seen transactions for wallet {wallet_address}, chat_id {chat_id}: {e}")
        return set()  # Return empty set on failure to keep bot running
    except Exception as e:
        logger.error(f"Unexpected error retrieving transactions for wallet {wallet_address}: {e}")
        return set()
    finally:
        if conn is not None:
            conn.close()
            logger.debug("Database connection closed after getting seen transactions")

def update_wallet_name(chat_id, wallet_address, custom_name):
    """Update the custom name for a wallet."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE user_wallets SET custom_name = ? WHERE chat_id = ? AND wallet_address = ?
        ''', (custom_name, chat_id, wallet_address))
        conn.commit()
        logger.info(f"Updated name for wallet {wallet_address} to '{custom_name}' for chat_id {chat_id}")
    except sqlite3.Error as e:
        logger.error(f"Failed to update wallet name for {wallet_address}, chat_id {chat_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating wallet name for {wallet_address}: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()
            logger.debug("Database connection closed after updating wallet name")
