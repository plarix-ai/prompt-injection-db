"""
Core corpus loader, indexer, and query engine.

Provides deterministic search and filtering over the prompt injection
database without requiring inference-heavy retrieval.
"""

from __future__ import annotations

import json
import math
import os
import re
import string
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REQUIRED_FIELDS = frozenset(
    [
        "id",
        "name",
        "title",
        "summary",
        "prompt",
        "prompt_text",
        "taxonomy",
        "category",
        "subcategory",
        "attack_family",
        "delivery_vector",
        "target_surface",
        "target_type",
        "tags",
        "status",
        "safe_internal_use_only",
        "postgres",
    ]
)

_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might can could and but or nor not no "
    "for to of in on at by from with as into through during before after "
    "above below between out off over under again further then once here "
    "there when where why how all each every both few more most other "
    "some such only own same so than too very this that these those it "
    "its he she they them their what which who whom".split()
)


# ---------------------------------------------------------------------------
# Tokeniser helpers (lightweight, no external deps)
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[{}]".format(re.escape(string.punctuation)))


def _tokenize(text: str) -> List[str]:
    """Lower-case, strip punctuation, remove stop words."""
    text = _PUNCT_RE.sub(" ", text.lower())
    return [w for w in text.split() if w and w not in _STOP_WORDS]


# ---------------------------------------------------------------------------
# BM25 index (minimal, stdlib-only implementation)
# ---------------------------------------------------------------------------


class _BM25Index:
    """Okapi BM25 ranking over a list of (doc_id, text) pairs."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._doc_ids: List[str] = []
        self._doc_lens: List[int] = []
        self._tf: List[Dict[str, int]] = []  # per-doc term frequencies
        self._df: Counter = Counter()  # document frequency per term
        self._avgdl: float = 0.0
        self._n: int = 0

    # -- build ---------------------------------------------------------------

    def add(self, doc_id: str, text: str) -> None:
        tokens = _tokenize(text)
        tf: Dict[str, int] = Counter(tokens)
        self._doc_ids.append(doc_id)
        self._doc_lens.append(len(tokens))
        self._tf.append(dict(tf))
        for term in set(tokens):
            self._df[term] += 1

    def build(self) -> None:
        self._n = len(self._doc_ids)
        self._avgdl = (
            sum(self._doc_lens) / self._n if self._n else 1.0
        )

    # -- query ---------------------------------------------------------------

    def query(self, text: str, top_k: int = 20) -> List[tuple]:
        """Return [(doc_id, score), ...] sorted descending by BM25 score."""
        terms = _tokenize(text)
        if not terms:
            return []
        scores: Dict[int, float] = defaultdict(float)
        for term in terms:
            if term not in self._df:
                continue
            idf = math.log(
                (self._n - self._df[term] + 0.5) / (self._df[term] + 0.5) + 1.0
            )
            for idx in range(self._n):
                tf_val = self._tf[idx].get(term, 0)
                if tf_val == 0:
                    continue
                dl = self._doc_lens[idx]
                num = tf_val * (self.k1 + 1)
                denom = tf_val + self.k1 * (
                    1 - self.b + self.b * dl / self._avgdl
                )
                scores[idx] += idf * num / denom
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [(self._doc_ids[idx], sc) for idx, sc in ranked[:top_k]]


# ---------------------------------------------------------------------------
# Inverted indexes for exact-match filtering
# ---------------------------------------------------------------------------


class _InvertedIndex:
    """Maps field values to sets of record IDs for O(1) lookup."""

    def __init__(self) -> None:
        self._index: Dict[str, Set[str]] = defaultdict(set)

    def add(self, value: str, record_id: str) -> None:
        self._index[value.lower()].add(record_id)

    def get(self, value: str) -> Set[str]:
        return set(self._index.get(value.lower(), set()))

    def all_keys(self) -> List[str]:
        return sorted(self._index.keys())


# ---------------------------------------------------------------------------
# PromptCorpus — main entry point
# ---------------------------------------------------------------------------


class PromptCorpus:
    """
    Loads, indexes, and queries the prompt injection corpus.

    Parameters
    ----------
    root : str or Path, optional
        Repository root.  Defaults to the parent of the ``adapter/`` dir.
    """

    def __init__(self, root: Optional[Union[str, Path]] = None):
        self._root = Path(root) if root else _REPO_ROOT
        self._records: Dict[str, Dict[str, Any]] = {}

        # Exact-match inverted indexes
        self._idx_category = _InvertedIndex()
        self._idx_subcategory = _InvertedIndex()
        self._idx_attack_family = _InvertedIndex()
        self._idx_delivery_vector = _InvertedIndex()
        self._idx_target_surface = _InvertedIndex()
        self._idx_target_type = _InvertedIndex()
        self._idx_tag = _InvertedIndex()
        self._idx_difficulty = _InvertedIndex()
        self._idx_stealth = _InvertedIndex()
        self._idx_status = _InvertedIndex()
        self._idx_context = _InvertedIndex()
        self._idx_capability = _InvertedIndex()

        # Full-text BM25 index
        self._bm25 = _BM25Index()

        self._load()

    # -- loading -------------------------------------------------------------

    def _load(self) -> None:
        """Discover and load all .postgres.json files under root."""
        for path in sorted(self._root.rglob("*.postgres.json")):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                continue
            rid = data.get("id")
            if not rid:
                continue
            data["_path"] = str(path.relative_to(self._root))
            self._records[rid] = data
            self._index_record(data)

        self._bm25.build()

    def _index_record(self, rec: Dict[str, Any]) -> None:
        rid = rec["id"]
        self._idx_category.add(rec.get("category", ""), rid)
        self._idx_subcategory.add(rec.get("subcategory", ""), rid)
        self._idx_attack_family.add(rec.get("attack_family", ""), rid)
        self._idx_delivery_vector.add(rec.get("delivery_vector", ""), rid)
        self._idx_target_surface.add(rec.get("target_surface", ""), rid)
        self._idx_target_type.add(rec.get("target_type", ""), rid)
        self._idx_difficulty.add(rec.get("difficulty", ""), rid)
        self._idx_stealth.add(rec.get("stealth", ""), rid)
        self._idx_status.add(rec.get("status", ""), rid)

        for tag in rec.get("tags", []):
            self._idx_tag.add(tag, rid)
        for ctx in rec.get("applicable_context", []):
            self._idx_context.add(ctx, rid)
        for cap in rec.get("agent_capability_targeted", []):
            self._idx_capability.add(cap, rid)

        # BM25: index title + summary + prompt_text + tags
        text_parts = [
            rec.get("title", ""),
            rec.get("summary", ""),
            rec.get("prompt_text", ""),
            " ".join(rec.get("tags", [])),
        ]
        self._bm25.add(rid, " ".join(text_parts))

    # -- public API ----------------------------------------------------------

    @property
    def size(self) -> int:
        """Total number of prompt records loaded."""
        return len(self._records)

    def ids(self) -> List[str]:
        """Return all record IDs sorted."""
        return sorted(self._records.keys())

    def get(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single record by ID."""
        return self._records.get(record_id)

    def all(self) -> List[Dict[str, Any]]:
        """Return all records as a list, sorted by ID."""
        return [self._records[k] for k in sorted(self._records)]

    def categories(self) -> List[str]:
        """List all unique category values."""
        return self._idx_category.all_keys()

    def subcategories(self) -> List[str]:
        """List all unique subcategory values."""
        return self._idx_subcategory.all_keys()

    def attack_families(self) -> List[str]:
        """List all unique attack_family values."""
        return self._idx_attack_family.all_keys()

    def tags(self) -> List[str]:
        """List all unique tag values."""
        return self._idx_tag.all_keys()

    def delivery_vectors(self) -> List[str]:
        """List all unique delivery_vector values."""
        return self._idx_delivery_vector.all_keys()

    def target_surfaces(self) -> List[str]:
        """List all unique target_surface values."""
        return self._idx_target_surface.all_keys()

    def target_types(self) -> List[str]:
        """List all unique target_type values."""
        return self._idx_target_type.all_keys()

    # -- filtering -----------------------------------------------------------

    def filter(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """
        Filter records by exact-match on indexed fields.

        Supported keyword arguments
        ---------------------------
        category, subcategory, attack_family, delivery_vector,
        target_surface, target_type, tag, difficulty, stealth,
        status, context, capability

        Multiple filters are AND-ed together.

        Returns list of matching records sorted by ID.
        """
        index_map = {
            "category": self._idx_category,
            "subcategory": self._idx_subcategory,
            "attack_family": self._idx_attack_family,
            "delivery_vector": self._idx_delivery_vector,
            "target_surface": self._idx_target_surface,
            "target_type": self._idx_target_type,
            "tag": self._idx_tag,
            "difficulty": self._idx_difficulty,
            "stealth": self._idx_stealth,
            "status": self._idx_status,
            "context": self._idx_context,
            "capability": self._idx_capability,
        }

        result_ids: Optional[Set[str]] = None
        for key, value in kwargs.items():
            idx = index_map.get(key)
            if idx is None:
                continue
            matches = idx.get(str(value))
            if result_ids is None:
                result_ids = matches
            else:
                result_ids = result_ids & matches

        if result_ids is None:
            return []
        return [self._records[rid] for rid in sorted(result_ids)]

    # -- full-text search ----------------------------------------------------

    def search(self, query: str, top_k: int = 20, **filters: Any) -> List[Dict[str, Any]]:
        """
        Combined BM25 keyword search + exact-match filtering.

        Parameters
        ----------
        query : str
            Free-text search query.
        top_k : int
            Maximum results to return.
        **filters
            Additional exact-match filters (same as ``filter()``).

        Returns ranked list of records (best match first).
        """
        # BM25 ranking
        ranked = self._bm25.query(query, top_k=top_k * 5)
        if not ranked:
            return []

        # Apply filters if any
        filter_ids: Optional[Set[str]] = None
        if filters:
            filter_results = self.filter(**filters)
            filter_ids = {r["id"] for r in filter_results}

        results = []
        for rid, _score in ranked:
            if filter_ids is not None and rid not in filter_ids:
                continue
            rec = self._records.get(rid)
            if rec:
                results.append(rec)
            if len(results) >= top_k:
                break
        return results

    # -- related & variants --------------------------------------------------

    def related(self, record_id: str) -> List[Dict[str, Any]]:
        """Return records listed in the related_prompts field."""
        rec = self.get(record_id)
        if not rec:
            return []
        return [
            self._records[rid]
            for rid in rec.get("related_prompts", [])
            if rid in self._records
        ]

    def variants(self, record_id: str) -> List[Dict[str, Any]]:
        """Return all records sharing the same subcategory code."""
        rec = self.get(record_id)
        if not rec:
            return []
        subcat = rec.get("subcategory", "")
        return self.filter(subcategory=subcat)

    # -- template / placeholder handling -------------------------------------

    def fill_template(
        self, record_id: str, **replacements: str
    ) -> Optional[str]:
        """
        Fill placeholder tokens in a prompt template.

        Placeholders in the prompt are ``[PLACEHOLDER_NAME]`` style.
        Pass replacements as keyword arguments, e.g.::

            corpus.fill_template("2.1-001", TARGET="synthesize methanol")

        Returns the filled prompt_text, or None if record not found.
        """
        rec = self.get(record_id)
        if not rec:
            return None
        text = rec.get("prompt_text", "")
        for key, val in replacements.items():
            text = text.replace(f"[{key.upper()}]", val)
        return text

    # -- export helpers ------------------------------------------------------

    def to_catalog(self) -> List[Dict[str, Any]]:
        """
        Export a lightweight catalog suitable for index files.

        Returns a list of dicts with core metadata (no full prompt text).
        """
        catalog = []
        for rid in sorted(self._records):
            rec = self._records[rid]
            catalog.append(
                {
                    "id": rec["id"],
                    "title": rec.get("title", rec.get("name", "")),
                    "summary": rec.get("summary", ""),
                    "category": rec.get("category", ""),
                    "subcategory": rec.get("subcategory", ""),
                    "attack_family": rec.get("attack_family", ""),
                    "delivery_vector": rec.get("delivery_vector", ""),
                    "target_surface": rec.get("target_surface", ""),
                    "target_type": rec.get("target_type", ""),
                    "difficulty": rec.get("difficulty", ""),
                    "stealth": rec.get("stealth", ""),
                    "realism": rec.get("realism", ""),
                    "tags": rec.get("tags", []),
                    "status": rec.get("status", ""),
                    "path": rec.get("_path", ""),
                }
            )
        return catalog

    def to_flat_export(self) -> List[Dict[str, Any]]:
        """
        Export all records as a flat list (full data minus internal fields).
        """
        results = []
        for rid in sorted(self._records):
            rec = dict(self._records[rid])
            rec.pop("_path", None)
            results.append(rec)
        return results

    def export_catalog_json(self, output_path: Optional[Union[str, Path]] = None) -> str:
        """Write the catalog to a JSON file and return the path."""
        if output_path is None:
            output_path = self._root / "exports" / "catalog.json"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(self.to_catalog(), fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        return str(output_path)

    def export_flat_json(self, output_path: Optional[Union[str, Path]] = None) -> str:
        """Write the full flat export to a JSON file and return the path."""
        if output_path is None:
            output_path = self._root / "exports" / "corpus_flat.json"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(self.to_flat_export(), fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        return str(output_path)

    def export_manifest(self, output_path: Optional[Union[str, Path]] = None) -> str:
        """Write a manifest of all lookup tables and metadata."""
        if output_path is None:
            output_path = self._root / "exports" / "manifest.json"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "total_records": self.size,
            "categories": self.categories(),
            "subcategories": self.subcategories(),
            "attack_families": self.attack_families(),
            "delivery_vectors": self.delivery_vectors(),
            "target_surfaces": self.target_surfaces(),
            "target_types": self.target_types(),
            "tags": self.tags(),
            "records": self.ids(),
        }
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        return str(output_path)
