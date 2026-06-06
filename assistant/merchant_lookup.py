"""
Lightweight online merchant lookup without paid API keys.

Uses DuckDuckGo instant answers and falls back to a simple heuristic description.
"""
import logging
import re

import requests

logger = logging.getLogger(__name__)

KNOWN_MERCHANTS = {
    'netflix': {'description': 'Netflix is a subscription streaming service for TV shows and movies.', 'is_subscription': True},
    'spotify': {'description': 'Spotify is a music and podcast streaming subscription service.', 'is_subscription': True},
    'amazon': {'description': 'Amazon is an online marketplace; charges may be purchases, Prime, or AWS.', 'is_subscription': False},
    'uber': {'description': 'Uber provides ride-hailing and food delivery services.', 'is_subscription': False},
    'lyft': {'description': 'Lyft is a ride-hailing service.', 'is_subscription': False},
    'apple': {'description': 'Apple charges may be App Store, iCloud, Apple Music, or device purchases.', 'is_subscription': False},
    'google': {'description': 'Google charges may be Google One, Play Store, Cloud, or Workspace.', 'is_subscription': False},
    'paypal': {'description': 'PayPal is a payment processor; the charge reflects the underlying merchant.', 'is_subscription': False},
    'stripe': {'description': 'Stripe is a payment processor; look for the merchant name in the description.', 'is_subscription': False},
    'whole foods': {'description': 'Whole Foods Market is a grocery store chain owned by Amazon.', 'is_subscription': False},
    'starbucks': {'description': 'Starbucks is a coffee shop chain.', 'is_subscription': False},
}


def lookup_merchant_online(merchant_name):
    normalized = merchant_name.strip().lower()

    for key, info in KNOWN_MERCHANTS.items():
        if key in normalized:
            return {
                'description': info['description'],
                'is_subscription': info['is_subscription'],
                'source': 'known_merchants',
            }

    try:
        response = requests.get(
            'https://api.duckduckgo.com/',
            params={'q': merchant_name, 'format': 'json', 'no_html': 1},
            timeout=5,
        )
        if response.status_code == 200:
            data = response.json()
            abstract = data.get('AbstractText', '')
            if abstract:
                return {
                    'description': abstract,
                    'source': 'duckduckgo',
                    'url': data.get('AbstractURL', ''),
                }
            related = data.get('RelatedTopics', [])
            if related and isinstance(related[0], dict):
                text = related[0].get('Text', '')
                if text:
                    return {'description': text, 'source': 'duckduckgo'}
    except Exception as e:
        logger.debug(f"DuckDuckGo lookup failed for {merchant_name}: {e}")

    clean = re.sub(r'\*+\d+|#\d+|pos\s', '', normalized, flags=re.IGNORECASE).strip()
    if clean:
        return {
            'description': f'"{merchant_name}" appears to be a merchant charge. Check your statement for the full descriptor.',
            'source': 'heuristic',
        }

    return None
