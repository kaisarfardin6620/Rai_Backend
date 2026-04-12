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
    api_key = getattr(settings, 'ODDS_API_KEY', 'your_api_key_here')
    url = f"https://api.the-odds-api.com/v4/sports/upcoming/odds/?regions=us&markets=spreads&apiKey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        for game in data[:10]:
            sport, _ = SportCategory.objects.get_or_create(name=game['sport_key'])
            match, _ = Match.objects.get_or_create(
                sport=sport,
                home_team=game['home_team'],
                away_team=game['away_team'],
                start_time=game['commence_time']
            )
            
            for bookmaker in game.get('bookmakers',[]):
                if bookmaker['key'] == 'draftkings':
                    market = bookmaker['markets'][0]
                    outcome = market['outcomes'][0]
                    
                    odds = outcome['price']
                    metrics = calculate_metrics(odds)
                    
                    Pick.objects.update_or_create(
                        match=match,
                        team_selected=outcome['name'],
                        defaults={
                            'pick_type': 'Spread',
                            'point_spread': outcome.get('point'),
                            'odds_american': odds,
                            'confidence_percentage': metrics['confidence'],
                            'edge_percentage': metrics['edge'],
                            'ev_percentage': metrics['ev']
                        }
                    )
        logger.info("sync_odds_completed")
    except Exception as e:
        logger.error("sync_odds_failed", error=str(e))