from app.scoring import score_events

def test_empty_event_list_is_normal():
    result = score_events([])
    assert result["score"] == 0
    assert result["category"] == "normal"
    assert result["reasons"] == []

def test_events_accumulate_and_are_explained():
    result = score_events([{"event_type": "multiple_faces", "duration_seconds": 20}])
    assert result["score"] > 0
    assert result["reasons"][0]["event_type"] == "multiple_faces"
    assert "not evidence of cheating" in result["disclaimer"]

def test_risk_is_bounded():
    result = score_events([{"event_type": "multiple_faces", "duration_seconds": 3600}] * 30)
    assert 0 <= result["score"] <= 100
    assert result["category"] == "high"
