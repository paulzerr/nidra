def scorer(scorer_type: str, **kwargs):
    """
    Factory function to create a scorer instance.

    Args:
        scorer_type (str): The type of scorer to create. Can be 'forehead' or 'psg'.
        **kwargs: Keyword arguments to pass to the scorer's constructor.

    Returns:
        An instance of the specified scorer class.
    """
    if scorer_type == 'forehead':
        from .forehead_scorer import ForeheadScorer
        return ForeheadScorer(**kwargs)
    elif scorer_type == 'psg':
        from .psg_scorer import PSGScorer
        return PSGScorer(**kwargs)
    else:
        raise ValueError(f"Unknown scorer type: {scorer_type}")

from .utils import batch_scorer
