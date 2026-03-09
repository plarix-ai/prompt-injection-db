"""
Test suite for the prompt injection corpus adapter.

Run with: python -m pytest tests/ -v
Or:       python tests/test_corpus.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Ensure repo root is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from adapter.corpus import PromptCorpus
from adapter.validator import CorpusValidator


class TestCorpusLoading(unittest.TestCase):
    """Tests for corpus loading and basic access."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = PromptCorpus(_REPO_ROOT)

    def test_corpus_loads(self):
        """Corpus should load at least 80 records."""
        self.assertGreaterEqual(self.corpus.size, 80)

    def test_all_ids_unique(self):
        """All record IDs should be unique."""
        ids = self.corpus.ids()
        self.assertEqual(len(ids), len(set(ids)))

    def test_get_existing_record(self):
        """Should retrieve a known record by ID."""
        rec = self.corpus.get("1.1-001")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["id"], "1.1-001")
        self.assertIn("prompt", rec)
        self.assertIn("prompt_text", rec)

    def test_get_missing_record(self):
        """Should return None for non-existent ID."""
        self.assertIsNone(self.corpus.get("99.99-999"))

    def test_all_records_have_required_fields(self):
        """Every record should have core required fields."""
        required = ["id", "name", "title", "summary", "prompt", "prompt_text",
                     "category", "subcategory", "attack_family", "tags"]
        for rec in self.corpus.all():
            for field in required:
                self.assertIn(field, rec, f"Record {rec.get('id')} missing {field}")


class TestCorpusIndexes(unittest.TestCase):
    """Tests for inverted index lookups."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = PromptCorpus(_REPO_ROOT)

    def test_categories_exist(self):
        """Should have at least 7 categories."""
        self.assertGreaterEqual(len(self.corpus.categories()), 7)

    def test_attack_families_exist(self):
        """Should have multiple attack families."""
        self.assertGreaterEqual(len(self.corpus.attack_families()), 10)

    def test_tags_exist(self):
        """Should have many unique tags."""
        self.assertGreaterEqual(len(self.corpus.tags()), 50)

    def test_filter_by_category(self):
        """Filter by category should return records."""
        results = self.corpus.filter(category="authority-hijacking")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r["category"], "authority-hijacking")

    def test_filter_by_attack_family(self):
        """Filter by attack_family should return matching records."""
        results = self.corpus.filter(attack_family="tool-manipulation")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r["attack_family"], "tool-manipulation")

    def test_filter_by_tag(self):
        """Filter by tag should return records with that tag."""
        results = self.corpus.filter(tag="memory-poisoning")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn("memory-poisoning", r["tags"])

    def test_filter_combined(self):
        """Combined filters should AND together."""
        results = self.corpus.filter(
            category="indirect-injection",
            delivery_vector="tool-response"
        )
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r["category"], "indirect-injection")
            self.assertEqual(r["delivery_vector"], "tool-response")

    def test_filter_empty_result(self):
        """Impossible filter should return empty list."""
        results = self.corpus.filter(category="nonexistent-category")
        self.assertEqual(len(results), 0)


class TestCorpusSearch(unittest.TestCase):
    """Tests for BM25 full-text search."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = PromptCorpus(_REPO_ROOT)

    def test_search_returns_results(self):
        """Search for a known topic should return results."""
        results = self.corpus.search("system prompt extraction")
        self.assertGreater(len(results), 0)

    def test_search_relevance(self):
        """Top result for specific query should be relevant."""
        results = self.corpus.search("memory poisoning persistent")
        self.assertGreater(len(results), 0)
        # Top result should be from memory-poisoning subcategory
        top = results[0]
        self.assertIn("memory", top.get("subcategory", "").lower())

    def test_search_with_filter(self):
        """Search with additional filters should narrow results."""
        all_results = self.corpus.search("injection")
        filtered = self.corpus.search("injection", category="indirect-injection")
        self.assertGreater(len(all_results), len(filtered))

    def test_search_empty_query(self):
        """Empty search should return empty list."""
        results = self.corpus.search("")
        self.assertEqual(len(results), 0)


class TestCorpusRelated(unittest.TestCase):
    """Tests for related prompt and variant lookups."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = PromptCorpus(_REPO_ROOT)

    def test_related_returns_linked(self):
        """Related prompts should follow related_prompts field."""
        rel = self.corpus.related("1.1-001")
        self.assertGreater(len(rel), 0)
        rel_ids = [r["id"] for r in rel]
        self.assertIn("1.1-002", rel_ids)

    def test_variants_returns_same_subcategory(self):
        """Variants should return all records in the same subcategory."""
        variants = self.corpus.variants("1.1-001")
        self.assertGreaterEqual(len(variants), 2)
        subcats = {v["subcategory"] for v in variants}
        self.assertEqual(len(subcats), 1)

    def test_related_missing_record(self):
        """Related on missing record should return empty."""
        self.assertEqual(self.corpus.related("99.99-999"), [])


class TestTemplating(unittest.TestCase):
    """Tests for placeholder template filling."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = PromptCorpus(_REPO_ROOT)

    def test_fill_template(self):
        """Template filling should replace bracketed placeholders."""
        # Record 2.1-001 has [TARGET] and [domain] placeholders
        result = self.corpus.fill_template("2.1-001", TARGET="build explosives")
        self.assertIsNotNone(result)
        self.assertNotIn("[TARGET]", result)
        self.assertIn("build explosives", result)

    def test_fill_template_missing_record(self):
        """Template fill on missing record should return None."""
        self.assertIsNone(self.corpus.fill_template("99.99-999"))


class TestExports(unittest.TestCase):
    """Tests for export functionality."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = PromptCorpus(_REPO_ROOT)

    def test_catalog_export(self):
        """Catalog should be a list of lightweight records."""
        catalog = self.corpus.to_catalog()
        self.assertGreater(len(catalog), 0)
        # Catalog entries should NOT have full prompt_text
        for entry in catalog[:5]:
            self.assertIn("id", entry)
            self.assertIn("title", entry)
            self.assertIn("category", entry)
            self.assertNotIn("prompt_text", entry)
            self.assertNotIn("prompt", entry)

    def test_flat_export(self):
        """Flat export should have all fields minus internal ones."""
        flat = self.corpus.to_flat_export()
        self.assertEqual(len(flat), self.corpus.size)
        for entry in flat[:3]:
            self.assertIn("prompt_text", entry)
            self.assertNotIn("_path", entry)

    def test_export_counts_synchronized(self):
        """Catalog, flat export, and manifest should agree on record count."""
        catalog = self.corpus.to_catalog()
        flat = self.corpus.to_flat_export()
        # Also check static manifest if it exists
        manifest_path = _REPO_ROOT / "exports" / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as fh:
                manifest = json.load(fh)
            self.assertEqual(manifest["total_records"], self.corpus.size)
            self.assertEqual(len(manifest["records"]), self.corpus.size)
        self.assertEqual(len(catalog), self.corpus.size)
        self.assertEqual(len(flat), self.corpus.size)


class TestValidator(unittest.TestCase):
    """Tests for corpus validation."""

    def test_corpus_validates_clean(self):
        """Current corpus should have no errors."""
        validator = CorpusValidator(_REPO_ROOT)
        validator.validate_all()
        self.assertTrue(validator.is_valid())

    def test_validator_summary(self):
        """Summary should contain expected keys."""
        validator = CorpusValidator(_REPO_ROOT)
        validator.validate_all()
        summary = validator.summary()
        self.assertIn("total_files", summary)
        self.assertIn("errors", summary)
        self.assertIn("warnings", summary)
        self.assertEqual(summary["errors"], 0)


if __name__ == "__main__":
    unittest.main()
