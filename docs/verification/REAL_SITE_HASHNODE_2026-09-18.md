# Real-site validation — nik-hil.hashnode.dev

**Date:** 2026-09-18
**Target URL:** https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling
**Job ID:** 47b0fca2-d183-444a-b07f-77870b0c0d14
**Mode:** live crawl (`demo_mode=false`), visibility provider=`demo` (llm_mention; no live LLM/search API keys)
**Status:** completed

## Crawl
- Pages fetched: see report JSON (orchestrator reported 15 × HTTP 200)
- SSRF: URL passed public-URL checks before fetch
- Seed article + series posts + homepage + tags crawled

## Health (health-v1)
- `aeo_health`: **72.7**
- `answerability`: **75.0**
- `content`: **70.7**
- `entity`: **32.5**
- `structured_data`: **90.0**
- `technical`: **95.0**
- Executive label: {'data_provenance': {'demo_mode': False, 'experiment_kind': 'llm_mention', 'health': 'derived_metric', 'retrieval_enabled': False}, 'major_caveats': ['LLM mention metrics are sample estimates from controlled llm-mention-v1 experiments, not AI search visibility or engine rankings.', 'Chat-completions / LLM mention probes (retrieval_enabled=false) are NOT equivalent to AI search visibility.', 'API-based observations are not equivalent to consumer ChatGPT, Gemini, or Perplexity UI results.', 'This product does not reproduce proprietary answer-engine ranking or retrieval.'], 'overall_health': {'formula_version': 'health-v1', 'label': 'good', 'score': 72.7}, 'strongest_areas': [{'component': 'technical', 'score': 95.0}, {'component': 'structured_data', 'score': 90.0}, {'component': 'answerability', 'score': 75.0}], 'top_3_actions': [{'code': 'REC_ADD_JSONLD_ORG', 'rank': 1, 'recommended_action': 'Publish valid Organization JSON-LD on the homepage.', 'title': 'Add Organization JSON-LD on the homepage'}, {'code': 'REC_CONSOLIDATE_BRAND_NAME', 'rank': 2, 'recommended_action': 'Pick one preferred brand spelling and use it consistently in titles and Organization schema.', 'title': 'Consolidate brand naming across titles'}, {'code': 'REC_ADD_CONTACT_OR_SAMEAS', 'rank': 3, 'recommended_action': 'Add sameAs profiles and a visible contact method on homepage or about.', 'title': 'Add contact or sameAs links'}], 'weakest_areas': [{'component': 'entity', 'score': 32.5}, {'component': 'content', 'score': 70.7}, {'component': 'answerability', 'score': 75.0}]}

## Site understanding (deterministic)
- Brand: Nikhil Ikhar's blog
- Industry guess: project_management ⚠️ likely misclassified for an AI/engineering blog
- Topics (sample): ['Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling', 'The agent loop', 'Our first two tools', 'Tool schemas', 'Implementing execute_code', 'The finish tool']
- Products/tags: ['#python', '#artificial-intelligence', '#software-engineering', '#llm', '#harness']
- Provenance: derived_metric

## Discovered queries
- Selected: 10
  - [brand] What is Nikhil Ikhar's blog?
  - [informational] What does Nikhil Ikhar's blog do?
  - [product_service] What products or services does Nikhil Ikhar's blog offer?
  - [alternatives] What are alternatives to Nikhil Ikhar's blog?
  - [comparison] How does Nikhil Ikhar's blog compare to other project management tools?
  - [commercial] How much does Nikhil Ikhar's blog cost?
  - [best_for] Is Nikhil Ikhar's blog good for teams?
  - [problem_solution] How can Nikhil Ikhar's blog help with #python?

## AI crawler access
- Agents analyzed: 10
- Caveat: robots.txt allow/disallow is an accessibility signal only. Allow does NOT imply AI search visibility, citation, or consumer-UI ranking.

## Visibility experiment
- experiment_kind: `llm_mention`
- retrieval_enabled: `False`
- provider: `demo`
- llm_mention_rate: {'denominator': 30, 'numerator': 0, 'provenance': 'synthetic_demo', 'value': 0.0}
- llm_url_mention_rate: {'denominator': 30, 'numerator': 0, 'provenance': 'synthetic_demo', 'value': 0.0}
- query_coverage: {'denominator': 10, 'numerator': 0, 'provenance': 'synthetic_demo', 'value': 0.0}
- Note: demo visibility provider → rates are **synthetic_demo**, not live LLM/API search observations

## Recommendations
- Count: 6
  - [1] Add Organization JSON-LD on the homepage
    urls: ['https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling']
  - [2] Consolidate brand naming across titles
    urls: ['https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling']
  - [3] Add contact or sameAs links
    urls: ['https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling']
  - [4] Clarify brand naming in on-page copy
    urls: ['https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling']
  - [5] Fix heading hierarchy
    urls: ['https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling', 'https://nik-hil.hashnode.dev/', 'https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling.md', 'https://nik-hil.hashnode.dev/series/agent-zero-2-hero', 'https://nik-hil.hashnode.dev/tag/python', 'https://nik-hil.hashnode.dev/tag/ai', 'https://nik-hil.hashnode.dev/tag/artificial-intelligence', 'https://nik-hil.hashnode.dev/tag/software-engineering', 'https://nik-hil.hashnode.dev/tag/llm', 'https://nik-hil.hashnode.dev/tag/harness', 'https://nik-hil.hashnode.dev/agents-zero-to-hero-2-giving-an-ai-agent-eyes-and-hands-filesystem-tools', 'https://nik-hil.hashnode.dev/agents-zero-to-hero-6-teaching-an-ai-agent-when-it-is-allowed-to-act', 'https://nik-hil.hashnode.dev/agents-zero-to-hero-5-making-an-ai-agent-provider-agnostic', 'https://nik-hil.hashnode.dev/agents-zero-to-hero-4-precise-code-editing-and-search-for-an-ai-coding-agent', 'https://nik-hil.hashnode.dev/agents-zero-to-hero-3-giving-an-ai-agent-a-shell-without-giving-it-your-machine']
  - [6] Publish stable, citable URLs in content

## Limitations
1. Visibility experiment used DemoProvider (no OPENAI/PERPLEXITY keys) — not AI-search visibility.
2. Site category heuristic guessed project_management (wrong for this blog) — affects some query templates.
3. No retrieval-enabled provider run → no competitor citation graph.
4. Site content not modified.

## Artifacts
- Full JSON: `docs/verification/REAL_SITE_47b0fca2.json`
