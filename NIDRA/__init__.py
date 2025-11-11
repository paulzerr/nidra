def scorer(type: str, **kwargs):
    """
    Factory function to create a scorer instance.
 
    Args:
        type (str): The type of scorer to create. Can be 'forehead' or 'psg'.
        **kwargs: Keyword arguments to pass to the scorer's constructor.
 
    Returns:
        An instance of the specified scorer class.
    """
    if type == 'forehead':
        from NIDRA.forehead_scorer import ForeheadScorer
        return ForeheadScorer(**kwargs)
    elif type == 'psg':
        from NIDRA.psg_scorer import PSGScorer
        return PSGScorer(**kwargs)
    else:
        raise ValueError(f"Unknown scorer type: {type}")
 
from NIDRA.utils import batch_scorer, find_files
