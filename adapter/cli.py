#!/usr/bin/env python3
"""
CLI tools for the prompt injection corpus.

Commands:
    validate   - Run validation checks on the corpus
    export     - Generate catalog, manifest, and flat export files
    search     - Search the corpus from command line
    stats      - Print corpus statistics

Usage:
    python -m adapter.cli validate
    python -m adapter.cli export
    python -m adapter.cli search "memory poisoning"
    python -m adapter.cli stats
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from adapter.corpus import PromptCorpus
from adapter.validator import CorpusValidator


def cmd_validate() -> int:
    """Run validation and report results."""
    print("Validating corpus...")
    validator = CorpusValidator(_REPO_ROOT)
    issues = validator.validate_all()
    summary = validator.summary()

    print(f"\nFiles scanned: {summary['total_files']}")
    print(f"Errors:        {summary['errors']}")
    print(f"Warnings:      {summary['warnings']}")
    print(f"Info:          {summary['info']}")

    if issues:
        print("\nIssues:")
        for issue in issues:
            print(f"  {issue}")

    if validator.is_valid():
        print("\n✓ Corpus is valid (no errors)")
        return 0
    else:
        print("\n✗ Corpus has errors")
        return 1


def cmd_export() -> None:
    """Generate all export files."""
    corpus = PromptCorpus(_REPO_ROOT)
    print(f"Loaded {corpus.size} records")

    catalog_path = corpus.export_catalog_json()
    print(f"Catalog exported to: {catalog_path}")

    flat_path = corpus.export_flat_json()
    print(f"Flat export to:      {flat_path}")

    manifest_path = corpus.export_manifest()
    print(f"Manifest exported to: {manifest_path}")

    print("\n✓ All exports generated")


def cmd_search(query: str, top_k: int = 10) -> None:
    """Search the corpus."""
    corpus = PromptCorpus(_REPO_ROOT)
    results = corpus.search(query, top_k=top_k)

    if not results:
        print(f"No results for: {query}")
        return

    print(f"Search results for: \"{query}\" ({len(results)} matches)\n")
    for i, rec in enumerate(results, 1):
        print(f"  {i}. [{rec['id']}] {rec.get('title', rec['name'])}")
        print(f"     Category: {rec.get('category', 'N/A')} | Family: {rec.get('attack_family', 'N/A')}")
        print(f"     {rec.get('summary', '')[:100]}...")
        print()


def cmd_stats() -> None:
    """Print corpus statistics."""
    corpus = PromptCorpus(_REPO_ROOT)

    print(f"Prompt Injection Corpus Statistics")
    print(f"{'=' * 50}")
    print(f"Total records:      {corpus.size}")
    print(f"Categories:         {len(corpus.categories())}")
    print(f"Subcategories:      {len(corpus.subcategories())}")
    print(f"Attack families:    {len(corpus.attack_families())}")
    print(f"Delivery vectors:   {len(corpus.delivery_vectors())}")
    print(f"Target surfaces:    {len(corpus.target_surfaces())}")
    print(f"Target types:       {len(corpus.target_types())}")
    print(f"Unique tags:        {len(corpus.tags())}")

    print(f"\nCategories:")
    for cat in corpus.categories():
        count = len(corpus.filter(category=cat))
        print(f"  {cat}: {count} records")

    print(f"\nAttack Families:")
    for fam in corpus.attack_families():
        count = len(corpus.filter(attack_family=fam))
        print(f"  {fam}: {count} records")

    print(f"\nDelivery Vectors:")
    for vec in corpus.delivery_vectors():
        count = len(corpus.filter(delivery_vector=vec))
        print(f"  {vec}: {count} records")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    cmd = sys.argv[1]

    if cmd == "validate":
        return cmd_validate()
    elif cmd == "export":
        cmd_export()
        return 0
    elif cmd == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not query:
            print("Usage: python -m adapter.cli search <query>")
            return 1
        cmd_search(query)
        return 0
    elif cmd == "stats":
        cmd_stats()
        return 0
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
