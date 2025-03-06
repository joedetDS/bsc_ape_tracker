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
        return sqlite3.connect(DB_FILE)
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def init_db():
    """Initialize the database with required tables."""
    try:
        # Ensure the directory exists
        db_dir = os.path.dirname(DB_FILE)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)  # Create directory if it doesn’t exist
        
        conn = None  # Initialize conn to None to avoid UnboundLocalError
        conn = get_connection()  # Attempt to establish connection
        cursor = conn.cursor()
        
        # Create necessary tables (example schema, adjust as needed)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_wallets (
                chat_id INTEGER,
                wallet_address TEXT,
                custom_name TEXT,
                PRIMARY KEY (chat_id, wallet_address)
            )
        ''')
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
        if conn:  # Only close conn if it was successfully created
            conn.close()
