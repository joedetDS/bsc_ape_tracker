import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

# Initialize Firebase
service_account_dict = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(service_account_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

def add_wallet(chat_id, wallet_address, custom_name=None):
    """Add a wallet to the user's watched list."""
    user_ref = db.collection('users').document(str(chat_id))
    wallet_ref = user_ref.collection('wallets').document(wallet_address)
    wallet_ref.set({
        'name': custom_name or '',
        'seen_txs': []
    })

def remove_wallet(chat_id, wallet_address):
    """Remove a wallet from the user's watched list."""
    user_ref = db.collection('users').document(str(chat_id))
    wallet_ref = user_ref.collection('wallets').document(wallet_address)
    wallet_ref.delete()

def get_wallets(chat_id):
    """Get all wallets the user is watching."""
    user_ref = db.collection('users').document(str(chat_id))
    wallets = user_ref.collection('wallets').get()
    return [(wallet.id, wallet.to_dict().get('name', '')) for wallet in wallets]

def add_seen_tx(chat_id, wallet_address, tx_hash):
    """Add a seen transaction for a wallet."""
    user_ref = db.collection('users').document(str(chat_id))
    wallet_ref = user_ref.collection('wallets').document(wallet_address)
    wallet_ref.update({
        'seen_txs': firestore.ArrayUnion([tx_hash])
    })

def get_seen_txs(chat_id, wallet_address):
    """Get all seen transactions for a wallet."""
    user_ref = db.collection('users').document(str(chat_id))
    wallet_ref = user_ref.collection('wallets').document(wallet_address)
    wallet_doc = wallet_ref.get()
    if wallet_doc.exists:
        return wallet_doc.to_dict().get('seen_txs', [])
    return []

def update_wallet_name(chat_id, wallet_address, new_name):
    """Update the custom name of a wallet."""
    user_ref = db.collection('users').document(str(chat_id))
    wallet_ref = user_ref.collection('wallets').document(wallet_address)
    wallet_ref.update({
        'name': new_name
    })
