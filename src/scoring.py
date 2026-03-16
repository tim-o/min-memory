# src/scoring.py

import math
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def compute_recency_score(created_at: str | None, half_life_days: float = 30.0) -> float:
    """Exponential decay from 1.0 (now) toward 0.0.

    Returns 0.0 for memories with no created_at (maximally old).
    """
    if not created_at:
        return 0.0
    try:
        created = datetime.fromisoformat(created_at)
        age_days = (datetime.now() - created).total_seconds() / 86400.0
        decay_lambda = math.log(2) / half_life_days
        return math.exp(-decay_lambda * max(age_days, 0.0))
    except (ValueError, TypeError):
        return 0.0


def blend_scores(similarity: float, recency: float, recency_weight: float) -> float:
    """Combine similarity and recency into a final ranking score."""
    return similarity * (1.0 - recency_weight) + recency * recency_weight
