"""Framework-independent progress reporting; observers cannot fail an analysis."""
import logging


def report_progress(callback, progress, stage):
    if callback is not None:
        try:
            callback(int(progress), stage)
        except Exception:
            logging.getLogger(__name__).exception("Progress observer failed")
