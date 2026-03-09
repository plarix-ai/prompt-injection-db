# Prompt Injection Corpus — Integration Guide

Internal documentation for integrating the prompt injection database with the authorized red-team evaluation infrastructure.

> **Safe for internal use only.** This corpus is designed for authorized internal testing against approved environments and fixtures.

---

## Quick Start

```python
from adapter import PromptCorpus

corpus = PromptCorpus()
print(f"Loaded {corpus.size} prompt records")

# Search for relevant prompts
results = corpus.search("tool manipulation MCP")
for r in results[:5]:
    print(f"  {r['id']} — {r['title']}")
```

---

## Schema

Each prompt record contains the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Unique identifier in `X.Y-NNN` format (e.g., `7.3-001`) |
| `name` | `string` | Human-readable name |
| `title` | `string` | Display title (may differ from name for variants) |
| `summary` | `string` | One-sentence description of what the prompt does |
| `prompt` | `string[]` | Prompt text as array of lines |
| `prompt_text` | `string` | Prompt text as a single joined string (for search) |
| `taxonomy` | `object` | Directory taxonomy metadata |
| `category` | `string` | Top-level attack category slug |
| `subcategory` | `string` | Subcategory slug |
| `attack_family` | `string` | Attack technique family |
| `delivery_vector` | `string` | How the prompt reaches the target |
| `target_surface` | `string` | What component is being attacked |
| `target_type` | `string` | Type of target system |
| `agent_capability_targeted` | `string[]` | Which agent capabilities are tested |
| `applicable_context` | `string[]` | Where the attack applies |
| `difficulty` | `string` | `low`, `medium`, or `high` |
| `stealth` | `string` | `low`, `medium`, or `high` |
| `realism` | `string` | `low`, `medium`, or `high` |
| `tags` | `string[]` | Searchable tags |
| `language` | `string` | Language code (e.g., `en`) |
| `format` | `string` | Content format (`text`, `json`, `code`, etc.) |
| `source` | `object` | Origin reference |
| `status` | `string` | `active`, `deprecated`, `draft`, `review` |
| `quality_score` | `number` | 1-5 quality rating |
| `last_reviewed` | `string` | ISO date of last review |
| `safe_internal_use_only` | `boolean` | Must always be `true` |
| `placeholders` | `string[]` | Template placeholders in the prompt |
| `related_prompts` | `string[]` | IDs of related prompt records |
| `mutation_guidance` | `string` | Hints for varying the prompt |
| `notes` | `string` | Additional context |
| `postgres` | `object` | PostgreSQL storage metadata |

---

## Adapter API

### Initialization

```python
from adapter import PromptCorpus

# Default: uses repo root auto-detected from adapter location
corpus = PromptCorpus()

# Or specify explicit path
corpus = PromptCorpus("/path/to/prompt-injection-db")
```

### Basic Access

```python
# Count records
corpus.size  # -> 82

# List all IDs
corpus.ids()  # -> ["1.1-001", "1.1-002", ...]

# Get a single record
rec = corpus.get("7.6-001")

# Get all records
all_records = corpus.all()
```

### Exact-Match Filtering

Use `.filter()` with keyword arguments. Multiple filters are AND-ed:

```python
# By category
corpus.filter(category="indirect-injection")

# By attack family
corpus.filter(attack_family="tool-manipulation")

# By tag
corpus.filter(tag="mcp-abuse")

# By target type
corpus.filter(target_type="tool-using-agent")

# By delivery vector
corpus.filter(delivery_vector="email-content")

# By difficulty
corpus.filter(difficulty="high")

# Combined
corpus.filter(category="indirect-injection", stealth="high")
```

Supported filter keys: `category`, `subcategory`, `attack_family`, `delivery_vector`, `target_surface`, `target_type`, `tag`, `difficulty`, `stealth`, `status`, `context`, `capability`.

### Full-Text Search (BM25)

```python
# Keyword search ranked by BM25
results = corpus.search("memory poisoning persistent agent")

# Search + filter
results = corpus.search("injection", category="indirect-injection")

# Limit results
results = corpus.search("system prompt", top_k=5)
```

### Related Prompts & Variants

```python
# Get related prompts (from related_prompts field)
related = corpus.related("7.6-001")

# Get all variants in same subcategory
variants = corpus.variants("7.6-001")
```

### Template Filling

Many prompts contain `[PLACEHOLDER]` tokens that can be filled:

```python
filled = corpus.fill_template("2.1-001",
    TARGET="exfiltrate database credentials",
    domain="cybersecurity"
)
print(filled)
```

### Listing Metadata

```python
corpus.categories()       # All category slugs
corpus.subcategories()    # All subcategory slugs
corpus.attack_families()  # All attack family slugs
corpus.tags()             # All unique tags
corpus.delivery_vectors() # All delivery vectors
corpus.target_surfaces()  # All target surfaces
corpus.target_types()     # All target types
```

---

## Export Formats

### Catalog (lightweight index)

```python
catalog = corpus.to_catalog()  # List of dicts without prompt text
corpus.export_catalog_json()   # Writes to exports/catalog.json
```

### Full Flat Export

```python
flat = corpus.to_flat_export()  # All records, flattened
corpus.export_flat_json()       # Writes to exports/corpus_flat.json
```

### Manifest

```python
corpus.export_manifest()  # Writes to exports/manifest.json
```

The manifest contains all lookup tables — categories, subcategories, attack families, delivery vectors, target surfaces, target types, tags, and record IDs.

---

## CLI Usage

```bash
# Validate the corpus
python -m adapter.cli validate

# Generate exports
python -m adapter.cli export

# Search
python -m adapter.cli search "MCP plugin tool abuse"

# Print statistics
python -m adapter.cli stats
```

---

## Adding New Prompts

1. Choose the correct category directory and subcategory folder.
2. Create a `.postgres.json` file following the naming pattern: `X.Y-NNN-slug.postgres.json`
3. Include all required schema fields.
4. Run validation: `python -m adapter.cli validate`
5. Regenerate exports: `python -m adapter.cli export`

### Example new record:

```json
{
  "id": "7.9-001",
  "name": "New Attack Pattern",
  "title": "New Attack Pattern",
  "summary": "Description of what this attack does.",
  "prompt": ["Line 1 of the attack prompt", "Line 2"],
  "prompt_text": "Line 1 of the attack prompt\nLine 2",
  "taxonomy": {
    "root_category": "INDIRECT / THIRD-PARTY INJECTION",
    "root_category_dir": "INDIRECT-INJECTION",
    "subcategory_code": "7.9",
    "subcategory_dir": "new-attack-pattern"
  },
  "category": "indirect-injection",
  "subcategory": "new-attack-pattern",
  "attack_family": "indirect-prompt-injection",
  "delivery_vector": "user-message",
  "target_surface": "target-component",
  "target_type": "agent-type",
  "agent_capability_targeted": ["capability-1"],
  "applicable_context": ["context-1"],
  "difficulty": "medium",
  "stealth": "high",
  "realism": "high",
  "tags": ["tag-1", "tag-2"],
  "language": "en",
  "format": "text",
  "source": {"file": "generated", "heading": "N/A"},
  "status": "active",
  "quality_score": 4,
  "last_reviewed": "2026-03-09",
  "safe_internal_use_only": true,
  "placeholders": [],
  "related_prompts": ["7.9-002"],
  "mutation_guidance": "How to vary this prompt.",
  "notes": "",
  "postgres": {
    "database": "postgresql",
    "storage_format": "jsonb",
    "table": "prompt_injection_prompts"
  }
}
```

---

## Deterministic Retrieval Design

The adapter is designed for deterministic retrieval using:

1. **Inverted indexes** for exact-match filtering on all metadata fields
2. **BM25 (Okapi)** for lexical keyword ranking — no neural inference needed
3. **Combined search+filter** for precise candidate retrieval

### Recommended integration pattern:

```python
from adapter import PromptCorpus

corpus = PromptCorpus()

# Step 1: Narrow by scenario attributes
candidates = corpus.filter(
    attack_family="tool-manipulation",
    target_type="tool-using-agent",
    stealth="high"
)

# Step 2: Rank by keyword relevance
ranked = corpus.search(
    "MCP server response poisoning",
    attack_family="tool-manipulation"
)

# Step 3: Get variants for diversity
for candidate in ranked[:3]:
    variants = corpus.variants(candidate["id"])

# Step 4: Fill templates
ready = corpus.fill_template(
    ranked[0]["id"],
    tool_name="web_fetch",
    system_prompt_reference="current system prompt"
)
```

---

## Validation

Run validation to ensure corpus integrity:

```python
from adapter import CorpusValidator

validator = CorpusValidator()
issues = validator.validate_all()

if not validator.is_valid():
    for issue in issues:
        print(issue)
```

Checks performed:
- Missing required fields
- Invalid enum values
- Malformed JSON
- Duplicate IDs
- Broken related_prompts references
- prompt_text / prompt array consistency
- Empty or too-short fields
- ID format compliance

---

## Directory Structure

```
prompt-injection-db/
├── AUTHORITY-HIJACKING/          # Category 1
│   ├── developer-creator-override/
│   ├── model-identity-reassignment/
│   ├── permission-escalation-fake-config/
│   ├── simulated-system-level-message-injection/
│   └── chain-of-command-spoofing/
├── CONTEXT-MANIPULATION/         # Category 2
├── SOCIO-EMOTIONAL-LEVERAGE/     # Category 3
├── OBFUSCATION-AND-MISDIRECTION/ # Category 4
│   └── metadata-annotation-injection/   (new)
├── INFORMATION-EXTRACTION/       # Category 5
│   └── data-exfiltration-via-tool-use/  (new)
├── STRUCTURAL-LOGICAL-EXPLOITATION/ # Category 6
│   ├── code-generation-injection/       (new)
│   └── context-window-poisoning/        (new)
├── INDIRECT-INJECTION/           # Category 7
│   ├── memory-poisoning/                (new)
│   ├── mcp-plugin-connector-abuse/      (new)
│   └── email-summarization-poisoning/   (new)
├── adapter/                      # Python adapter
│   ├── __init__.py
│   ├── corpus.py                 # Core loader + search
│   ├── validator.py              # Validation engine
│   └── cli.py                    # CLI tools
├── exports/                      # Generated index files
│   ├── catalog.json
│   ├── corpus_flat.json
│   └── manifest.json
├── tests/
│   └── test_corpus.py
├── INTEGRATION.md                # This file
└── README.md
```
