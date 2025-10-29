from flask import Flask, request, jsonify
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# API Keys
CRYPTOPANIC_API_KEY = os.environ.get('CRYPTOPANIC_API_KEY', '')
NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', '')

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

@app.route('/search', methods=['POST'])
def search():
    """
    Main search endpoint that the agent will call
    Expected request format:
    {
        "query": "user query string",
        "filter": "optional filter",
        "metadata": {}
    }
    """
    try:
        data = request.get_json()
        query = data.get('query', '')
        filter_param = data.get('filter', '')
        
        # Fetch crypto news based on query
        news_results = fetch_crypto_news(query, filter_param)
        
        # Format response according to agent schema
        response = {
            "search_results": news_results
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        print(f"Error in search endpoint: {e}")
        return jsonify({
            "error": str(e),
            "search_results": []
        }), 500

def fetch_crypto_news(query, filter_param=''):
    """
    Fetch crypto news from multiple sources
    """
    results = []
    
    # Source 1: CoinGecko Trending (Always works - no key needed)
    coingecko_results = fetch_from_coingecko(query)
    results.extend(coingecko_results)
    
    # Source 2: CryptoPanic (if API key is available)
    if CRYPTOPANIC_API_KEY:
        cryptopanic_results = fetch_from_cryptopanic(query)
        results.extend(cryptopanic_results)
    
    # Source 3: CoinGecko Market Data
    market_results = fetch_crypto_prices(query)
    results.extend(market_results)
    
    # Source 4: NewsAPI for crypto news (if key available)
    if NEWSAPI_KEY:
        news_results = fetch_from_newsapi(query)
        results.extend(news_results)
    
    # Limit to top 10 results and sort by relevance score
    results.sort(key=lambda x: x.get('result_metadata', {}).get('score', 0), reverse=True)
    return results[:10]

def fetch_from_cryptopanic(query):
    """
    Fetch news from CryptoPanic API
    """
    results = []
    
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_API_KEY}&public=true"
        
        # Add filter for specific coins
        coin_filters = {
            'bitcoin': 'BTC',
            'btc': 'BTC',
            'ethereum': 'ETH',
            'eth': 'ETH',
            'solana': 'SOL',
            'sol': 'SOL'
        }
        
        query_lower = query.lower()
        for keyword, currency in coin_filters.items():
            if keyword in query_lower:
                url += f"&currencies={currency}"
                break
        
        print(f"Fetching from CryptoPanic: {url}")
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            for post in data.get('results', [])[:5]:
                results.append({
                    "result_metadata": {
                        "score": calculate_relevance_score(query, post.get('title', ''))
                    },
                    "title": post.get('title', ''),
                    "body": (
                        f"{post.get('title', '')}. "
                        f"{post.get('source', {}).get('title', '')} - "
                        f"Published: {post.get('published_at', '')}"
                    ),
                    "url": post.get('url', ''),
                    "highlight": {
                        "body": [
                            post.get('title', ''),
                            f"Source: {post.get('source', {}).get('title', 'Unknown')}",
                            f"Votes: {post.get('votes', {}).get('positive', 0)}"
                        ]
                    }
                })
        else:
            print(f"CryptoPanic API error: {response.status_code} - {response.text}")
    
    except Exception as e:
        print(f"Error fetching from CryptoPanic: {e}")
    
    return results

def fetch_from_coingecko(query):
    """
    Fetch trending coins from CoinGecko
    """
    results = []
    
    try:
        url = "https://api.coingecko.com/api/v3/search/trending"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            for coin in data.get('coins', [])[:3]:
                coin_data = coin.get('item', {})
                results.append({
                    "result_metadata": {
                        "score": calculate_relevance_score(query, coin_data.get('name', ''))
                    },
                    "title": f"🔥 {coin_data.get('name', '')} ({coin_data.get('symbol', '').upper()}) - Trending",
                    "body": (
                        f"{coin_data.get('name', '')} is currently trending on CoinGecko. "
                        f"Market Cap Rank: #{coin_data.get('market_cap_rank', 'N/A')}. "
                        f"Price: ${coin_data.get('data', {}).get('price', 'N/A')}"
                    ),
                    "url": f"https://www.coingecko.com/en/coins/{coin_data.get('id', '')}",
                    "highlight": {
                        "body": [
                            f"🔥 Trending: {coin_data.get('name', '')}",
                            f"Rank: #{coin_data.get('market_cap_rank', 'N/A')}",
                            f"24h Volume: ${coin_data.get('data', {}).get('total_volume', 'N/A')}"
                        ]
                    }
                })
    
    except Exception as e:
        print(f"Error fetching from CoinGecko trending: {e}")
    
    return results

def fetch_crypto_prices(query):
    """
    Fetch current prices for major cryptocurrencies
    """
    results = []
    
    # Map common queries to coin IDs
    coin_map = {
        'bitcoin': 'bitcoin',
        'btc': 'bitcoin',
        'ethereum': 'ethereum',
        'eth': 'ethereum',
        'solana': 'solana',
        'sol': 'solana',
        'cardano': 'cardano',
        'ada': 'cardano',
        'xrp': 'ripple',
        'ripple': 'ripple'
    }
    
    query_lower = query.lower()
    coin_ids = []
    
    # Check if specific coin is mentioned
    for keyword, coin_id in coin_map.items():
        if keyword in query_lower:
            coin_ids.append(coin_id)
    
    # If no specific coin, get top coins
    if not coin_ids:
        coin_ids = ['bitcoin', 'ethereum', 'solana']
    
    try:
        ids = ','.join(coin_ids)
        url = (
            "https://api.coingecko.com/api/v3/simple/price"
            f"?ids={ids}&vs_currencies=usd"
            "&include_24hr_change=true&include_market_cap=true"
        )
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            for coin_id, price_data in data.items():
                change_24h = price_data.get('usd_24h_change', 0)
                emoji = "📈" if change_24h > 0 else "📉"
                
                results.append({
                    "result_metadata": {
                        "score": 0.9
                    },
                    "title": f"{emoji} {coin_id.capitalize()} Price Update",
                    "body": (
                        f"{coin_id.capitalize()} is trading at ${price_data.get('usd', 0):,.2f} "
                        f"with a 24h change of {change_24h:.2f}%. "
                        f"Market Cap: ${price_data.get('usd_market_cap', 0):,.0f}"
                    ),
                    "url": f"https://www.coingecko.com/en/coins/{coin_id}",
                    "highlight": {
                        "body": [
                            f"Price: ${price_data.get('usd', 0):,.2f}",
                            f"24h Change: {change_24h:.2f}%",
                            f"Market Cap: ${price_data.get('usd_market_cap', 0):,.0f}"
                        ]
                    }
                })
    
    except Exception as e:
        print(f"Error fetching crypto prices: {e}")
    
    return results

def fetch_from_newsapi(query):
    """
    Fetch crypto news from NewsAPI.org
    Sign up at: https://newsapi.org (100 requests/day free)
    """
    results = []
    
    try:
        # Search for crypto-related news
        url = (
            "https://newsapi.org/v2/everything?q=cryptocurrency OR bitcoin OR ethereum"
            f"&apiKey={NEWSAPI_KEY}&sortBy=publishedAt&pageSize=5"
        )
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            for article in data.get('articles', [])[:3]:
                results.append({
                    "result_metadata": {
                        "score": calculate_relevance_score(query, article.get('title', ''))
                    },
                    "title": article.get('title', ''),
                    "body": article.get('description', '') or article.get('content', '')[:200],
                    "url": article.get('url', ''),
                    "highlight": {
                        "body": [
                            article.get('title', ''),
                            f"Source: {article.get('source', {}).get('name', 'Unknown')}",
                            f"Published: {article.get('publishedAt', '')}"
                        ]
                    }
                })
    
    except Exception as e:
        print(f"Error fetching from NewsAPI: {e}")
    
    return results

def calculate_relevance_score(query, text):
    """
    Simple relevance scoring based on keyword matching
    Returns a score between 0 and 1
    """
    if not query or not text:
        return 0.5
    
    query_lower = query.lower()
    text_lower = text.lower()
    
    # Check for exact matches
    if query_lower in text_lower:
        return 0.95
    
    # Check for keyword matches
    query_words = [w for w in query_lower.split() if len(w) > 3]
    if not query_words:
        return 0.5
    
    matches = sum(1 for word in query_words if word in text_lower)
    
    return 0.5 + (matches / len(query_words)) * 0.4

@app.route('/', methods=['GET'])
def home():
    """Root endpoint with API info"""
    return jsonify({
        "service": "Crypto News API",
        "version": "2.0",
        "status": "running",
        "data_sources": {
            "coingecko": "✅ Active (Trending coins & prices)",
            "cryptopanic": "✅ Active" if CRYPTOPANIC_API_KEY else "⚠️ No API key",
            "newsapi": "✅ Active" if NEWSAPI_KEY else "⚠️ No API key"
        },
        "endpoints": {
            "/search": "POST - Main search endpoint",
            "/health": "GET - Health check"
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Crypto News API on port {port}...")
    print(f"CryptoPanic API: {'✅ Configured' if CRYPTOPANIC_API_KEY else '⚠️ Not configured'}")
    print(f"NewsAPI: {'✅ Configured' if NEWSAPI_KEY else '⚠️ Not configured'}")
    app.run(host='0.0.0.0', port=port, debug=True)
