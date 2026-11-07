"""Transparent heuristic aggregation; a review aid, never a cheating classifier."""
WEIGHTS = {"looking_away": 8, "face_absent": 12, "multiple_faces": 18, "camera_lost": 3, "head_deviation": 7}

def score_events(events: list[dict]) -> dict:
    contributions = {}
    for event in events:
        kind = event.get("event_type", "")
        weight = WEIGHTS.get(kind, 0)
        duration = max(1.0, float(event.get("duration_seconds", 1)))
        # Duration adds modestly; repeated events accumulate and the final score is capped.
        contributions[kind] = contributions.get(kind, 0) + weight * min(2.0, 0.5 + duration / 20)
    score = min(100, round(sum(contributions.values())))
    category = "normal" if score < 30 else "low" if score < 50 else "moderate" if score < 75 else "high"
    return {"score": score, "category": category, "event_count": len(events), "reasons": [{"event_type": k, "points": round(v)} for k, v in contributions.items()], "disclaimer": "Behavioural signals can have benign causes. Score is not evidence of cheating; human review is required."}
