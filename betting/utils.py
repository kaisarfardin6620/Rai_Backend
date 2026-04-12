def american_to_decimal(american_odds):
    if american_odds > 0:
        return (american_odds / 100) + 1
    else:
        return (100 / abs(american_odds)) + 1

def calculate_implied_probability(american_odds):
    decimal_odds = american_to_decimal(american_odds)
    return (1 / decimal_odds) * 100

def calculate_metrics(odds, sharp_implied_prob=None):
    implied_prob = calculate_implied_probability(odds)
    confidence = int(implied_prob)
    
    edge = 2.5 if odds > 0 else 0.5
    ev = edge * 1.2 

    return {
        "confidence": confidence,
        "edge": round(edge, 2),
        "ev": round(ev, 2)
    }