"""ResearchWitness: offline, deterministic verification of explicitly formalized claim witnesses."""
from .capsule import VERSION, evaluate, load_bundle, subject_digest
from .strict import Invalid

__all__ = ['VERSION', 'Invalid', 'evaluate', 'load_bundle', 'subject_digest']
__version__ = VERSION
