"""Module-relative snapshot location and explicit local development CORS."""
import os
from pathlib import Path
from urllib.parse import urlsplit

DATA_DIR = Path(__file__).resolve().parent / "data"
API_TITLE = "Fire Monitor Retrospective Review API"
API_VERSION = "1.0.0"
CLASSIFICATION_SOURCE = "rule_based_weak_label_fallback"
DISCLAIMER = "This API serves a retrospective demonstration dataset. Classes are rule-based weak-label categories, and risk scores rank detections for human review. They are not verified fire causes, probabilities, severity measurements or emergency-dispatch recommendations."
SOURCE_HASHES = {
    "data/processed/classified_hotspots.csv": "29031a9049f145574c507fba40e6d94b3760052e2d199287d3934d2733b614cf",
    "outputs/hotspot_risk_audit.csv": "17ebd97e8b40d584df095b654ffd5746bbe8a66532e8f350562806482bcc8dd7",
    "outputs/high_priority_alerts.csv": "6b4fc985fc0456c6af941904bd946c5fe9b6c6169d96f4d2f2c5d3f6bac732be",
    "outputs/daily_alert_summary.csv": "d919a3c31475502790b5b8c8328d22b7c6853ca513de96d02ef8f8595e56c02a",
    "outputs/risk_score_distribution.csv": "2396498a177c248639ab3cd354c41e069ba4401de60f27dbfbbfa4466439d15d",
}


def cors_origins() -> tuple[str, ...]:
    origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    for origin in os.environ.get("FIRE_MONITOR_CORS_ORIGINS", "").split(","):
        origin = origin.strip()
        if not origin:
            continue
        url = urlsplit(origin)
        try:
            port = url.port
        except ValueError as exc:
            raise ValueError("Invalid explicit CORS origin") from exc
        if "*" in origin or url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
            raise ValueError("CORS origins must be explicit HTTP(S) origins without paths, credentials or wildcards")
        if origin not in origins:
            origins.append(origin)
    return tuple(origins)
