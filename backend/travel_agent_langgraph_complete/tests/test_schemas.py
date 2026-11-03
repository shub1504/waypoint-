from app.schemas import IntentResult, TravelPreferences

def test_intent():
    x = IntentResult(is_travel=True, confidence=0.99, reason="trip planning")
    assert x.is_travel

def test_preferences():
    x = TravelPreferences(origin="Delhi", destination="Manali")
    assert x.destination == "Manali"
