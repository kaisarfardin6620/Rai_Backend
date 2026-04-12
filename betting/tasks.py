# betting/tasks.py
import structlog
import requests
from celery import shared_task
from django.conf import settings
from .models import Match, Pick, SportCategory
from .utils import calculate_metrics

logger = structlog.get_logger(__name__)

@shared_task
def sync_odds_data():
    logger.info("sync_odds_started")
    api_key = getattr(settings, 'THE_ODDS_API_KEY', 'your_api_key_here')
    
    # CHANGED: 'h2h' (Moneyline) is always available, unlike spreads.
    url = f"https://api.the-odds-api.com/v4/sports/upcoming/odds/?regions=us&markets=h2h&oddsFormat=american&apiKey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # Check if the API returned an error message
        if isinstance(data, dict) and "message" in data:
            logger.error("odds_api_error_message", message=data["message"])
            return

        for game in data[:1000]:
            sport, _ = SportCategory.objects.get_or_create(name=game['sport_key'])
            match, _ = Match.objects.get_or_create(
                sport=sport,
                home_team=game['home_team'],
                away_team=game['away_team'],
                start_time=game['commence_time']
            )
            
            bookmakers = game.get('bookmakers', [])
            if not bookmakers:
                continue
                
            # FALLBACK SYSTEM: Look for DraftKings. If not found, use the first bookmaker available!
            selected_bookmaker = None
            for bookie in bookmakers:
                if bookie['key'] == 'draftkings':
                    selected_bookmaker = bookie
                    break
            
            if not selected_bookmaker:
                selected_bookmaker = bookmakers[0] # Grab whatever bookie is there
                
            for market in selected_bookmaker.get('markets', []):
                for outcome in market.get('outcomes', []):
                    odds = outcome['price']
                    metrics = calculate_metrics(odds)
                    
                    Pick.objects.update_or_create(
                        match=match,
                        team_selected=outcome['name'],
                        defaults={
                            'pick_type': 'Moneyline',
                            'odds_american': odds,
                            'confidence_percentage': metrics['confidence'],
                            'edge_percentage': metrics['edge'],
                            'ev_percentage': metrics['ev']
                        }
                    )
        logger.info("sync_odds_completed")
    except Exception as e:
        logger.error("sync_odds_failed", error=str(e))