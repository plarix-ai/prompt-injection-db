"""
Prompt Injection Corpus Adapter
================================
Programmatic access to the prompt injection database for internal
authorized red-team evaluation infrastructure.

Usage:
    from adapter import PromptCorpus

    corpus = PromptCorpus()
    results = corpus.search(attack_family="tool-manipulation", tags=["mcp-abuse"])
    for r in results:
        print(r["id"], r["title"])

Safe for internal use only. Not intended for production deployment
against external targets.
"""

from adapter.corpus import PromptCorpus
from adapter.validator import CorpusValidator

__all__ = ["PromptCorpus", "CorpusValidator"]
__version__ = "1.0.0"
