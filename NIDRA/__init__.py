from NIDRA.utils import batch_scorer as _batch_scorer

def scorer(type: str, **kwargs):
    return _batch_scorer(type=type, **kwargs)
