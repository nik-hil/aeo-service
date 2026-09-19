# Phase 7 — Ready-to-publish homepage pack

**Status: NOT PUBLISHED**  
Live CMS change is **blocked** without an authorized `HASHNODE_PAT` / Hashnode owner session.  
This file is the copy-paste pack for CoS once credentials arrive.

Source recommendations (do not invent new ones): `PHASE6_RECOMMENDATION_EXAMPLES.json`

| Code | Intent |
| --- | --- |
| `REC_CONSOLIDATE_BRAND_NAME` | One preferred brand spelling in titles + Organization schema |
| `REC_CLARIFY_BRAND_IN_COPY` | Preferred brand in titles, lead, schema `name` |
| `REC_FIX_HEADING_HIERARCHY` | One `h1`; sequential `h2`→`h3` |

Machine-readable twin: `PHASE7_READY_TO_PUBLISH.json`

---

## Preferred brand

**Preferred string:** `Nikhil Ikhar`  
Verified live (2026-09-19): homepage still uses **`Nikhil Ikhar's blog`** for title / og / about card / Blog JSON-LD publisher; **`h1` is still missing**.  
Person name `Nikhil Ikhar` is the Phase 6 / Phase 3 entity signal to consolidate on.

Do **not** change the URL `https://nik-hil.hashnode.dev/`.

### Brand string list (before → after)

| Field | Before | After |
| --- | --- | --- |
| Document / publication title | `Nikhil Ikhar's blog` | `Nikhil Ikhar` |
| Header / nav label | `Nikhil Ikhar's blog` | `Nikhil Ikhar` |
| About card name | `Nikhil Ikhar's blog` | `Nikhil Ikhar` |
| Footer label | `Nikhil Ikhar's blog` | `Nikhil Ikhar` |
| Blog / publisher JSON-LD `name` | `Nikhil Ikhar's blog` | `Nikhil Ikhar` |

---

## Exact H1 to add

```text
Nikhil Ikhar
```

HTML:

```html
<h1>Nikhil Ikhar</h1>
```

Homepage must have **exactly one** `h1`. Do not add this H1 to individual article pages (they already have article-title H1s).

---

## Exact lead / about blurb

```text
Nikhil Ikhar writes practical guides on building AI agents with tool calling, secure shells, filesystem tools, and multi-provider harnesses.
```

HTML:

```html
<p>Nikhil Ikhar writes practical guides on building AI agents with tool calling, secure shells, filesystem tools, and multi-provider harnesses.</p>
```

### Exact meta description

```text
Nikhil Ikhar: AI agents, tool calling, MLOps, and Python tutorials.
```

---

## Exact Organization / Person JSON-LD

Valid JSON-LD (paste into Hashnode head / custom code injection):

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Person",
      "@id": "https://nik-hil.hashnode.dev/#person",
      "name": "Nikhil Ikhar",
      "url": "https://nik-hil.hashnode.dev/",
      "sameAs": [
        "https://github.com/nik-hil",
        "https://www.linkedin.com/in/nikhar",
        "https://hashnode.com/@TechNikhil"
      ]
    },
    {
      "@type": "Organization",
      "@id": "https://nik-hil.hashnode.dev/#organization",
      "name": "Nikhil Ikhar",
      "url": "https://nik-hil.hashnode.dev/",
      "founder": {"@id": "https://nik-hil.hashnode.dev/#person"},
      "sameAs": [
        "https://github.com/nik-hil",
        "https://www.linkedin.com/in/nikhar",
        "https://hashnode.com/@TechNikhil"
      ]
    }
  ]
}
</script>
```

---

## Heading hierarchy — Hashnode UI notes

**Current live outline (homepage):**

- `h1`: **missing**
- `h2`: Command Palette (dialog); Latest articles (listing label, often sr-only)
- `h3`: article card titles

**Target outline:**

1. One visible `h1` → `Nikhil Ikhar`
2. Keep `Latest articles` as `h2`
3. Keep article cards as `h3` (do not promote)

### What to click / edit in Hashnode

1. **Dashboard → Blog → Appearance / General** — set Blog title / Publication name to `Nikhil Ikhar`.
2. **Dashboard → Blog → Appearance / SEO (or About)** — set description to the exact meta description above; set About text to the exact lead blurb.
3. **Dashboard → Blog → Custom / Head / Code Injection** — paste the JSON-LD `<script>` block above into the **head**.
4. **Homepage H1** — default Hashnode listing themes often render the publication name as a link/`<p>`, not `<h1>`. Use custom injection or an About/Pages block so the homepage emits exactly:

   ```html
   <h1>Nikhil Ikhar</h1>
   <p>Nikhil Ikhar writes practical guides on building AI agents with tool calling, secure shells, filesystem tools, and multi-provider harnesses.</p>
   ```

5. **Save / Publish** — record `published_at` when CoS completes publish.
6. **View Source** on `https://nik-hil.hashnode.dev/` — confirm one H1, brand consolidation, and JSON-LD.

---

## NOT PUBLISHED

| Gate | Value |
| --- | --- |
| Live CMS write | **NOT DONE** |
| `HASHNODE_PAT` in this env | **absent** |
| Post-change measurement | **NOT RUN** |
| Causal impact | **NOT ESTABLISHED** |

After publish, remeasure with:

```bash
python scripts/phase7_post_publish_remeasure.py
```

Defaults lock seed `3236362228`, `provider=openai_compatible`, `llm_mention` only, `paid_retrieval_opt_in=false` (ADR-026 closed).
