"""MatchVision API exports, loaded lazily so health checks do not import YOLO."""
__all__ = ["AnalysisError", "analyze_match"]


def __getattr__(name):
    if name in __all__:
        from .analysis import AnalysisError, analyze_match
        return {"AnalysisError": AnalysisError, "analyze_match": analyze_match}[name]
    raise AttributeError(name)
