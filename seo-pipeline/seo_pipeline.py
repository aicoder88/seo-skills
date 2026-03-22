#!/usr/bin/env python3
"""
SEO Pipeline — Automated keyword-to-article factory.

Every run:
  1. DISCOVER  — expand seed keywords via Google Suggest
  2. ANALYZE   — score each keyword (SERP competition + intent + trends)
  3. CREATE    — write full SEO articles for the best opportunities
  4. SAVE      — markdown files with YAML frontmatter, ready to publish

Usage:
  python3 seo_pipeline.py              # single run
  python3 seo_pipeline.py --daemon     # loop every N hours (from config)
  python3 seo_pipeline.py --once       # force one article right now
  python3 seo_pipeline.py --status     # show queue and stats

Requirements:
  pip3 install anthropic pytrends
  ANTHROPIC_API_KEY, SERPER_API_KEY (2500 free at serper.dev),
  GOOGLE_API_KEY (25k/day free at console.developers.google.com)
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("ERROR: Run: pip3 install anthropic")
    sys.exit(1)

# ─── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = Path(__file__).parent
CONFIG_PATH  = SCRIPT_DIR / "config.json"
STATE_PATH   = SCRIPT_DIR / "pipeline_state.json"
FREE_SEO     = Path.home() / ".claude/skills/seo-freedata/scripts/free_seo_data.py"

# ─── Big-brand domains — high competition signal in SERP ─────────────────────

BIG_BRANDS = {
    "google", "amazon", "youtube", "facebook", "wikipedia", "reddit",
    "linkedin", "twitter", "instagram", "tiktok", "pinterest", "yelp",
    "microsoft", "apple", "shopify", "hubspot", "salesforce", "mailchimp",
    "forbes", "businessinsider", "techcrunch", "nytimes", "theguardian",
    "healthline", "webmd", "mayo", "investopedia", "nerdwallet",
}

# ─── Article generation system prompt ────────────────────────────────────────

ARTICLE_SYSTEM_PROMPT = """You are an expert SEO content writer. Write comprehensive, engaging articles
optimized for both search engines and real readers.

CONTENT RULES:
- Match search intent (informational → guide/tutorial, commercial → comparison/review,
  transactional → product/landing page)
- Primary keyword in H1, first 100 words, and naturally throughout body
- Keyword density: 0.5–1.5%
- Reading level: Grade 8–10
- Paragraph length: 2–3 sentences max
- Vary sentence length: mix short punchy sentences with longer explanations

E-E-A-T (non-negotiable):
- Include at least one first-person experience example or specific anecdote
- Include at least one cited data point or statistic
- Show expertise through accurate, specific details
- Transparent, trustworthy claims only

STRUCTURE (follow for every article):
  H1: Primary keyword + compelling hook
  [Intro 50–100 words: hook the reader, state the value, keyword in first 2 sentences]
  H2: [Main topic 1]
    H3: [Subtopic if needed]
  H2: [Main topic 2]
  H2: [Practical examples / how-to]
  H2: Frequently Asked Questions
    [3–5 Q&A pairs targeting People Also Ask]
  H2: [Summary / Next Steps]
    [CTA aligned with search intent]

BANNED WRITING PATTERNS (never use):
- Em dashes (—) — replace with commas, colons, or parentheses
- "In today's world / digital age / fast-paced world"
- "Let's delve into" / "delve"
- "That being said" / "With that in mind" / "At its core"
- "In conclusion" / "To sum up" / "All things considered"
- "transformative", "cutting-edge", "groundbreaking", "seamless", "robust"
- "comprehensive", "pivotal", "nuanced", "holistic", "multifaceted"
- "leverage" (use: use/apply) / "utilize" (use: use) / "foster" (use: encourage)
- "Whether you're a [X], [Y], or [Z]..."
- Starting sentences with "By [gerund]..." ("By understanding X, you can Y")

OUTPUT: Return ONLY valid JSON (no markdown code fences), exactly this structure:
{
  "article": "# H1 Title\\n\\n[full markdown article here]",
  "title_tags": [
    "Title Option 1 | Brand (XX chars)",
    "Title Option 2 | Brand (XX chars)",
    "Title Option 3 | Brand (XX chars)"
  ],
  "meta_description": "150–160 char description with primary keyword and CTA.",
  "url_slug": "primary-keyword-slug",
  "key_takeaways": ["Takeaway 1", "Takeaway 2", "Takeaway 3"],
  "schema_type": "Article",
  "word_count": 0
}"""


# ─── Helpers ─────────────────────────────────────────────────────────────────

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    symbols = {"INFO": "·", "OK": "✓", "WARN": "⚠", "ERR": "✗", "HEAD": "▶"}
    print(f"[{ts}] {symbols.get(level, '·')} {msg}", flush=True)


def run_free_seo(command, arg, env=None):
    """Run a free_seo_data.py command, return parsed JSON or None."""
    if not FREE_SEO.exists():
        log(f"seo-freedata not found at {FREE_SEO}", "ERR")
        return None
    merged_env = {**os.environ, **(env or {})}
    try:
        result = subprocess.run(
            [sys.executable, str(FREE_SEO), command, arg],
            capture_output=True, text=True, timeout=30, env=merged_env
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        log(f"free_seo {command} '{arg}': {e}", "WARN")
    return None


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_]+", "-", text)


def count_words(text):
    return len(re.findall(r"\b\w+\b", text))


# ─── Config & State ───────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "seed_keywords": ["example keyword"],
    "site_url": "https://yoursite.com",
    "site_name": "Your Site",
    "site_type": "blog",
    "output_dir": str(SCRIPT_DIR / "output"),
    "interval_hours": 4,
    "articles_per_run": 3,
    "target_word_count": 1500,
    "model": "claude-opus-4-6",
    "min_score": 4,
    "max_keyword_queue": 200,
}


def load_config():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
        log(f"Created default config at {CONFIG_PATH} — edit it before running", "WARN")
        sys.exit(0)
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    return {**DEFAULT_CONFIG, **cfg}


def load_state():
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {
        "keyword_queue": [],          # [{keyword, score, intent, trend, serp_data, added_at}]
        "analyzed_keywords": {},      # keyword → analysis data
        "written_articles": {},       # keyword → {file, created_at, word_count}
        "last_run": None,
        "total_articles": 0,
        "total_keywords_found": 0,
    }


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))


# ─── Phase 1: Discover ────────────────────────────────────────────────────────

def discover_keywords(cfg, state):
    """Expand seed keywords using Google Suggest. Add new ones to queue."""
    seeds = cfg["seed_keywords"]
    known = (
        set(state["analyzed_keywords"].keys())
        | {item["keyword"] for item in state["keyword_queue"]}
        | set(state["written_articles"].keys())
    )
    new_found = 0

    for seed in seeds:
        log(f"Discovering from seed: '{seed}'")
        data = run_free_seo("suggest", seed)
        if not data:
            continue

        suggestions = data.get("suggestions", [])
        # Also treat the seed itself as a candidate
        candidates = [seed] + suggestions

        for kw in candidates:
            kw = kw.strip().lower()
            if not kw or kw in known or len(kw) < 3:
                continue
            if len(state["keyword_queue"]) >= cfg["max_keyword_queue"]:
                break
            state["keyword_queue"].append({
                "keyword": kw,
                "score": 0,
                "intent": "unknown",
                "trend": "unknown",
                "serp_urls": [],
                "added_at": datetime.now().isoformat(),
            })
            known.add(kw)
            new_found += 1
        time.sleep(1)  # rate limit

    state["total_keywords_found"] += new_found
    log(f"Discovery: {new_found} new keywords queued ({len(state['keyword_queue'])} total)", "OK")
    return state


# ─── Phase 2: Analyze ─────────────────────────────────────────────────────────

def score_keyword(serp_data, intent_data, trends_data):
    """
    Score 0–10 based on intent value, trend direction, and competition.
    Higher = better opportunity.
    """
    score = 0

    # Intent (0–4)
    intent = "unknown"
    if intent_data:
        intent = intent_data.get("primary_intent", "unknown")
    intent_score = {"transactional": 4, "commercial": 3, "informational": 2,
                    "navigational": 1, "unknown": 1}
    score += intent_score.get(intent, 1)

    # Trend (0–3)
    trend = "unknown"
    if trends_data and not trends_data.get("error"):
        trend = trends_data.get("trend_direction", "unknown")
    trend_score = {"rising": 3, "stable": 2, "falling": 0, "unknown": 1}
    score += trend_score.get(trend, 1)

    # Competition from SERP (0–3)
    serp_urls = []
    if serp_data and not serp_data.get("error"):
        results = serp_data.get("results", [])
        serp_urls = [r.get("url", "") for r in results[:10]]
        top_domains = [r.get("domain", "") for r in results[:5]]
        brand_count = sum(
            1 for d in top_domains
            if any(b in d for b in BIG_BRANDS)
        )
        if brand_count == 0:
            score += 3
        elif brand_count <= 2:
            score += 2
        elif brand_count <= 3:
            score += 1

    return score, intent, trend, serp_urls


def analyze_keywords(cfg, state, max_analyze=30):
    """Score up to max_analyze un-scored queued keywords."""
    unscored = [item for item in state["keyword_queue"] if item["score"] == 0]
    to_analyze = unscored[:max_analyze]

    if not to_analyze:
        log("No keywords to analyze")
        return state

    log(f"Analyzing {len(to_analyze)} keywords...")

    for item in to_analyze:
        kw = item["keyword"]
        log(f"  → analyzing '{kw}'")

        serp   = run_free_seo("serp",   kw);  time.sleep(1)
        intent = run_free_seo("intent", kw);  time.sleep(1)
        trends = run_free_seo("trends", kw);  time.sleep(2)

        score, intent_type, trend_dir, serp_urls = score_keyword(serp, intent, trends)

        item["score"]     = score
        item["intent"]    = intent_type
        item["trend"]     = trend_dir
        item["serp_urls"] = serp_urls[:5]

        state["analyzed_keywords"][kw] = {
            "score": score,
            "intent": intent_type,
            "trend": trend_dir,
            "serp_urls": serp_urls[:5],
            "people_also_ask": (serp or {}).get("people_also_ask", []),
            "related_searches": (serp or {}).get("related_searches", []),
            "analyzed_at": datetime.now().isoformat(),
        }
        log(f"  {kw} → score {score}/10 | intent: {intent_type} | trend: {trend_dir}", "OK")

    # Sort queue: highest score first, skip already written
    written = set(state["written_articles"].keys())
    state["keyword_queue"] = sorted(
        [item for item in state["keyword_queue"] if item["keyword"] not in written],
        key=lambda x: x["score"],
        reverse=True,
    )

    save_state(state)
    return state


# ─── Phase 3: Write articles ──────────────────────────────────────────────────

def build_article_prompt(kw_data, cfg):
    """Build the user prompt for article generation."""
    keyword   = kw_data["keyword"]
    intent    = kw_data.get("intent", "informational")
    trend     = kw_data.get("trend", "stable")
    serp_urls = kw_data.get("serp_urls", [])
    paa       = kw_data.get("people_also_ask", [])
    related   = kw_data.get("related_searches", [])

    competitor_block = ""
    if serp_urls:
        competitor_block = "\n\nCURRENTLY RANKING URLS (study these, then do better):\n"
        competitor_block += "\n".join(f"  {u}" for u in serp_urls[:5])

    paa_block = ""
    if paa:
        paa_block = "\n\nPEOPLE ALSO ASK (answer these in your FAQ section):\n"
        paa_block += "\n".join(f"  - {q}" for q in paa[:5])

    related_block = ""
    if related:
        related_block = "\n\nRELATED SEARCHES (use as semantic variations):\n"
        related_block += ", ".join(str(r) for r in related[:8])

    return f"""Write a complete SEO article for the following:

TARGET KEYWORD: {keyword}
SEARCH INTENT: {intent}
TREND: {trend}
TARGET WORD COUNT: {cfg['target_word_count']}+ words
SITE NAME: {cfg['site_name']}
SITE TYPE: {cfg['site_type']}
SITE URL: {cfg['site_url']}
{competitor_block}{paa_block}{related_block}

REQUIREMENTS:
1. H1 must contain "{keyword}" naturally
2. First paragraph must include "{keyword}" within the first 2 sentences
3. Use related searches as semantic variations throughout
4. Answer ALL People Also Ask questions in the FAQ section
5. Conclude with a CTA appropriate for a {cfg['site_type']} site
6. Word count must reach {cfg['target_word_count']} words minimum

Return ONLY the JSON object. No preamble, no code fences."""


def generate_article(kw_data, cfg, client):
    """Call Anthropic API to write the article. Returns parsed article dict or None."""
    keyword = kw_data["keyword"]
    log(f"Writing article: '{keyword}'")

    prompt = build_article_prompt(kw_data, cfg)

    try:
        full_text = ""
        with client.messages.stream(
            model=cfg["model"],
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=ARTICLE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                full_text += text
        print()  # newline after streaming

        # Parse JSON from response
        # Strip any accidental code fences
        clean = re.sub(r"^```(?:json)?\s*", "", full_text.strip(), flags=re.MULTILINE)
        clean = re.sub(r"\s*```$", "", clean.strip(), flags=re.MULTILINE)

        article_data = json.loads(clean)

        # Fill in actual word count
        article_text = article_data.get("article", "")
        article_data["word_count"] = count_words(article_text)

        log(f"Article written: {article_data['word_count']} words", "OK")
        return article_data

    except json.JSONDecodeError as e:
        log(f"JSON parse failed for '{keyword}': {e}", "ERR")
        log(f"Raw output (first 300 chars): {full_text[:300]}", "ERR")
        return None
    except anthropic.RateLimitError:
        log("Anthropic rate limit hit — sleeping 60s", "WARN")
        time.sleep(60)
        return None
    except Exception as e:
        log(f"Article generation error for '{keyword}': {e}", "ERR")
        return None


def save_article(keyword, article_data, cfg, state):
    """Save article as markdown with YAML frontmatter."""
    output_dir = Path(cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = article_data.get("url_slug") or slugify(keyword)
    filename = f"{slug}.md"
    filepath = output_dir / filename

    # Build frontmatter
    title_tags    = article_data.get("title_tags", [])
    primary_title = title_tags[0] if title_tags else keyword
    meta_desc     = article_data.get("meta_description", "")
    takeaways     = article_data.get("key_takeaways", [])
    schema_type   = article_data.get("schema_type", "Article")
    word_count    = article_data.get("word_count", 0)

    frontmatter = f"""---
title: "{primary_title}"
description: "{meta_desc}"
slug: "{slug}"
keyword: "{keyword}"
intent: "{state['analyzed_keywords'].get(keyword, {}).get('intent', 'unknown')}"
trend: "{state['analyzed_keywords'].get(keyword, {}).get('trend', 'unknown')}"
schema_type: "{schema_type}"
word_count: {word_count}
generated_at: "{datetime.now().isoformat()}"
title_variations:
{chr(10).join(f'  - "{t}"' for t in title_tags)}
key_takeaways:
{chr(10).join(f'  - "{t}"' for t in takeaways)}
---

"""

    content = frontmatter + article_data.get("article", "")
    filepath.write_text(content, encoding="utf-8")

    state["written_articles"][keyword] = {
        "file": str(filepath),
        "slug": slug,
        "word_count": word_count,
        "created_at": datetime.now().isoformat(),
    }
    state["total_articles"] += 1

    log(f"Saved: {filepath.name} ({word_count} words)", "OK")
    return filepath


# ─── Main pipeline run ────────────────────────────────────────────────────────

def run_pipeline(cfg, state, client, force_one=False):
    log("=" * 50, "HEAD")
    log(f"SEO Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M')}", "HEAD")
    log("=" * 50, "HEAD")

    # Phase 1: Discover
    state = discover_keywords(cfg, state)
    save_state(state)

    # Phase 2: Analyze (up to 20 per run to stay within rate limits)
    state = analyze_keywords(cfg, state, max_analyze=20)
    save_state(state)

    # Phase 3: Write articles
    min_score   = cfg["min_score"]
    articles_n  = 1 if force_one else cfg["articles_per_run"]
    written     = set(state["written_articles"].keys())

    candidates = [
        item for item in state["keyword_queue"]
        if item["keyword"] not in written
        and item["score"] >= min_score
    ]

    if not candidates:
        log(f"No keywords with score ≥ {min_score} ready. Lower min_score in config or add more seeds.", "WARN")
    else:
        log(f"Writing {min(articles_n, len(candidates))} articles (best opportunities)...")

    articles_written = 0
    for item in candidates[:articles_n]:
        kw       = item["keyword"]
        kw_data  = {
            **item,
            **(state["analyzed_keywords"].get(kw, {})),
        }
        article_data = generate_article(kw_data, cfg, client)
        if article_data:
            save_article(kw, article_data, cfg, state)
            articles_written += 1
        save_state(state)
        time.sleep(3)  # brief pause between articles

    # Summary
    log("─" * 50)
    log(f"Run complete: {articles_written} articles written")
    log(f"Total articles ever: {state['total_articles']}")
    log(f"Keywords in queue: {len(state['keyword_queue'])}")
    log(f"Output directory: {cfg['output_dir']}")
    state["last_run"] = datetime.now().isoformat()
    save_state(state)


# ─── Status report ────────────────────────────────────────────────────────────

def print_status(cfg, state):
    print("\n── SEO Pipeline Status ──────────────────────")
    print(f"  Last run:         {state.get('last_run', 'never')}")
    print(f"  Articles written: {state['total_articles']}")
    print(f"  Keywords found:   {state['total_keywords_found']}")
    print(f"  Queue size:       {len(state['keyword_queue'])}")

    written = set(state["written_articles"].keys())
    scored = [(i["keyword"], i["score"], i["intent"], i["trend"])
              for i in state["keyword_queue"]
              if i["score"] > 0 and i["keyword"] not in written]
    scored.sort(key=lambda x: -x[1])

    if scored:
        print(f"\n  Top queued opportunities (score/10):")
        for kw, sc, intent, trend in scored[:10]:
            print(f"    [{sc:2d}] {kw:<40} intent={intent} trend={trend}")

    if state["written_articles"]:
        print(f"\n  Recent articles:")
        recent = sorted(state["written_articles"].items(),
                        key=lambda x: x[1].get("created_at", ""),
                        reverse=True)[:5]
        for kw, info in recent:
            print(f"    · {kw:<40} {info['word_count']} words  {info['file'].split('/')[-1]}")
    print()


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SEO Pipeline")
    parser.add_argument("--daemon",  action="store_true", help="Loop every N hours")
    parser.add_argument("--once",    action="store_true", help="Force write 1 article now")
    parser.add_argument("--status",  action="store_true", help="Show queue and stats")
    args = parser.parse_args()

    cfg   = load_config()
    state = load_state()

    if args.status:
        print_status(cfg, state)
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        log("ANTHROPIC_API_KEY not set. Export it or add to ~/.zshrc", "ERR")
        sys.exit(1)

    client = anthropic.Anthropic()

    if args.daemon:
        interval = cfg["interval_hours"] * 3600
        log(f"Daemon mode: running every {cfg['interval_hours']} hours. Ctrl+C to stop.")

        def handle_sigint(sig, frame):
            log("Shutting down gracefully...")
            sys.exit(0)
        signal.signal(signal.SIGINT, handle_sigint)

        while True:
            state = load_state()  # reload in case manually edited
            run_pipeline(cfg, state, client)
            next_run = datetime.fromtimestamp(time.time() + interval)
            log(f"Next run at {next_run.strftime('%H:%M:%S')} — sleeping {cfg['interval_hours']}h")
            time.sleep(interval)
    else:
        run_pipeline(cfg, state, client, force_one=args.once)


if __name__ == "__main__":
    main()
