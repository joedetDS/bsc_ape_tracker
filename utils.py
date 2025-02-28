from web3 import Web3
import requests
from config import WEB3_PROVIDER_URL, BSCSCAN_API_KEY

# Initialize Web3 connection
web3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URL))

def get_bnb_balance(wallet_address: str) -> float:
    """Get BNB balance of a wallet."""
    balance_wei = web3.eth.get_balance(Web3.to_checksum_address(wallet_address))
    return web3.from_wei(balance_wei, 'ether')

def get_bnb_price() -> float:
    """Fetch current BNB price in USD from CoinGecko."""
    url = "https://api.coingecko.com/api/v3/simple/price?ids=binancecoin&vs_currencies=usd"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get("binancecoin", {}).get("usd", 0.0)
    return 0.0

def get_token_market_cap(contract_address: str) -> float:
    """Fetch the token's market cap in USD from CoinGecko."""
    url = f"https://api.coingecko.com/api/v3/coins/binance-smart-chain/contract/{contract_address}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data.get("market_data", {}).get("market_cap", {}).get("usd", 0.0)
    return 0.0

def get_token_balances(wallet_address: str) -> list:
    """Fetch BEP-20 token balances using BscScan API."""
    url = (f"https://api.bscscan.com/api?module=account&action=tokentx&address={wallet_address}"
           f"&startblock=0&endblock=99999999&sort=desc&apikey={BSCSCAN_API_KEY}")
    response = requests.get(url)
    if response.status_code != 200:
        return []
    
    data = response.json()
    if data["status"] != "1" or "result" not in data:
        return []
    
    token_balances = {}
    for tx in data["result"]:
        token_symbol = tx["tokenSymbol"]
        token_address = tx["contractAddress"]
        token_decimal = int(tx["tokenDecimal"])
        token_value = int(tx["value"]) / (10 ** token_decimal)
        
        # Aggregate token balances by contract address
        if token_address in token_balances:
            token_balances[token_address]["balance"] += token_value
        else:
            token_balances[token_address] = {
                "symbol": token_symbol,
                "balance": token_value,
                "contract_address": token_address
            }
    
    return list(token_balances.values())

def get_last_transactions(wallet_address: str) -> dict:
    """Fetch the last buy and sell transactions of the wallet (including contract address)."""
    url = (f"https://api.bscscan.com/api?module=account&action=tokentx&address={wallet_address}"
           f"&startblock=0&endblock=99999999&sort=desc&apikey={BSCSCAN_API_KEY}")
    response = requests.get(url)
    if response.status_code != 200:
        return {"buy": None, "sell": None}
    
    data = response.json()
    if data["status"] != "1" or "result" not in data:
        return {"buy": None, "sell": None}

    last_buy, last_sell = None, None

    for tx in data["result"]:
        tx_type = "buy" if tx["to"].lower() == wallet_address.lower() else "sell"
        tx_details = {
            "symbol": tx["tokenSymbol"],
            "amount": int(tx["value"]) / (10 ** int(tx["tokenDecimal"])),
            "tx_hash": tx["hash"],
            "timestamp": int(tx["timeStamp"]),
            "contract_address": tx["contractAddress"]
        }
        
        if tx_type == "buy" and last_buy is None:
            last_buy = tx_details
        elif tx_type == "sell" and last_sell is None:
            last_sell = tx_details

        if last_buy and last_sell:
            break

    return {"buy": last_buy, "sell": last_sell}
