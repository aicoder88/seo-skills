---
name: seo-freedata
description: >
  Free SEO data commands replacing DataForSEO. Provides keyword suggestions,
  Google Trends, PageSpeed Insights (Core Web Vitals), SERP results, tech stack
  detection, WHOIS lookup, and search intent classification — all free or near-free.
  Use when user says "keyword research", "search trends", "page speed", "tech stack",
  "WHOIS", "search intent", "free SEO data", or asks for live data without DataForSEO.
user-invokable: true
argument-hint: "[command] [query]"
allowed-tools:
  - Read
  - Bash
  - WebFetch
  - Write
  - Glob
  - Grep
---

# Free SEO Data

Free replacement for the DataForSEO extension. Uses Google's free APIs,
pytrends, WHOIS services, and optional cheap APIs (Serper.dev).

## Quick Reference

| Command | What it does | Cost |
|---------|-------------|------|
| `/seo-freedata suggest <keyword>` | Google Autocomplete suggestions | Free always |
| `/seo-freedata trends <keyword>` | Google Trends 12-month interest | Free always |
| `/seo-freedata psi <url>` | PageSpeed Insights + Core Web Vitals | Free (25k/day with API key) |
| `/seo-freedata serp <keyword>` | Live SERP top 10 | Free (Serper.dev 2500 signup) |
| `/seo-freedata tech <url>` | Tech stack from headers + HTML | Free always |
| `/seo-freedata whois <domain>` | Domain registration data | Free always |
| `/seo-freedata intent <keyword>` | Search intent classification | Free always |

## Setup (Optional — Improves Results)

Two optional API keys unlock better data. Both are free to start:

```bash
# PageSpeed Insights: 25,000 free requests/day
# Get key: console.developers.google.com → Enable "PageSpeed Insights API"
export GOOGLE_API_KEY=your_key_here

# Live SERP results: 2,500 free searches on signup, then ~$50/50k
# Get key: serper.dev (60-second signup)
export SERPER_API_KEY=your_key_here
```

Without keys, PSI still works (low rate limit) and SERP falls back to Google Suggest.

## Running Commands

All commands use the Python script:

```bash
SCRIPT=~/.claude/skills/seo-freedata/scripts/free_seo_data.py

# Keyword suggestions
python $SCRIPT suggest "email marketing software"

# Google Trends
python $SCRIPT trends "ai seo tools"

# PageSpeed Insights
python $SCRIPT psi https://example.com

# SERP (needs SERPER_API_KEY for live results)
SERPER_API_KEY=xxx python $SCRIPT serp "best crm for startups"

# Tech detection
python $SCRIPT tech https://example.com

# WHOIS
python $SCRIPT whois example.com

# Intent classification
python $SCRIPT intent "how to write meta descriptions"
```

---

## Command Details

### `suggest <keyword>`

Google Autocomplete — the same suggestions Google shows in the search box.

**Use for:**
- Long-tail keyword discovery
- Content topic variations
- People Also Ask-style questions

**Output:** List of 8-10 keyword suggestions.

---

### `trends <keyword>`

Google Trends interest over 12 months via pytrends.

**Use for:**
- Seasonal content planning (when to publish)
- Validating whether interest is rising or falling
- Comparing two topics (run twice, compare averages)

**Output:** Trend direction (rising/stable/falling), weekly interest series (0-100 relative scale), peak month.

**Limitation:** Values are relative (0-100), not absolute search volumes. A score of 100 = peak interest for that keyword, not 100 searches.

---

### `psi <url>`

Google PageSpeed Insights — real Lighthouse data via Google's API.

**Use for:**
- Core Web Vitals audit (LCP, TBT/INP proxy, CLS)
- Performance score (mobile + desktop)
- Finding specific slow resources to fix

**Output:** Scores for performance, SEO, accessibility, best practices. CWV values with good/needs-improvement/poor status. Top 5 opportunities with estimated savings.

**Key note:** TBT (Total Blocking Time) is the lab proxy for INP. Field INP data comes from CrUX, not available via this API. For field data, use Google Search Console's Core Web Vitals report.

---

### `serp <keyword>`

Top 10 Google results.

**With SERPER_API_KEY (recommended):** Live positions, titles, snippets, People Also Ask, Related Searches, SERP features detected (featured snippet, knowledge panel, PAA).

**Without key (fallback):** Returns Google Suggest results + intent classification. No positions.

**Use for:**
- Understanding what Google considers best content for a keyword
- Identifying competitor domains
- Confirming search intent before writing content
- Finding People Also Ask questions to answer

---

### `tech <url>`

Detects CMS, framework, CDN, analytics, payment processors, and marketing tools from HTTP response headers and HTML patterns.

**Detects:** WordPress, Shopify, Squarespace, Wix, Webflow, Framer, Next.js, Nuxt, Gatsby, Astro, React, Vue, Angular, Cloudflare, Fastly, CloudFront, BunnyCDN, Netlify, Vercel, Cloudflare Pages, Tailwind, Bootstrap, Google Analytics/GTM, Plausible, Hotjar, Segment, Intercom, Stripe, HubSpot, Salesforce, and schema types in use.

**Use for:**
- Competitor tech stack research
- Identifying what CMS a site uses before pitching or auditing
- Verifying CDN usage for performance decisions

**Note:** For deeper detection, install Wappalyzer CLI: `npm i -g wappalyzer`

---

### `whois <domain>`

Domain registration data via RDAP (IANA-backed, always free).

**Returns:** Registrar, creation date, expiration date, nameservers, domain status.

**Use for:**
- Checking domain age (older = more trust)
- Verifying expiration before it lapses
- Competitor domain intelligence

---

### `intent <keyword>`

Classifies keyword into: **informational** / **commercial** / **transactional** / **navigational**.

Uses keyword pattern matching + Google Suggest signals. Upgrade to SERP-verified classification by running `serp` first.

**Content type mapping:**

| Intent | Write This |
|--------|-----------|
| Informational | Blog post, guide, tutorial, FAQ |
| Commercial | Comparison, review, "best X" list |
| Transactional | Product page, landing page, pricing page |
| Navigational | Homepage, brand page |

---

## DataForSEO vs Free: Capability Map

| DataForSEO Command | Free Equivalent | Quality |
|-------------------|----------------|---------|
| `serp <keyword>` | `serp` via Serper.dev | ✅ Excellent |
| `trends <keyword>` | `trends` via pytrends | ✅ Excellent |
| `keywords <seed>` | `suggest` via Autocomplete | ✅ Good |
| `intent <keywords>` | `intent` via pattern analysis | ✅ Good |
| `onpage <url>` | `psi` via PageSpeed Insights | ✅ Good |
| `tech <domain>` | `tech` via header+HTML analysis | ✅ Good |
| `whois <domain>` | `whois` via RDAP | ✅ Excellent |
| `volume <keywords>` | pytrends (relative only) | ⚠️ Limited |
| `difficulty <keywords>` | SERP competition analysis | ⚠️ Limited |
| `backlinks <domain>` | No free equivalent | ❌ Not available |
| `ranked <domain>` | Google Search Console (own site) | ✅ Good (own site) |
| `competitors <domain>` | SERP competitor domain list | ⚠️ Limited |
| `traffic <domains>` | No reliable free equivalent | ❌ Not available |
| `ai-mentions <keyword>` | No free equivalent | ❌ Not available |

**For absolute keyword volumes and backlinks:** No free option exists. Ahrefs ($99/mo) and Semrush ($99/mo) are the standards. Moz has 10 free link queries/month.

---

## Integration with claude-seo

When this skill is active, other claude-seo skills can use it for live data:

- **seo-audit**: Run `psi` for real CWV data, `tech` for stack detection
- **seo-content**: Run `serp` + `intent` before writing to confirm what's ranking
- **seo-page**: Run `psi` to get actual performance scores
- **seo-plan**: Run `serp` for competitor domains, `trends` for topic seasonality
- **seo-technical**: Run `psi` for Core Web Vitals, `whois` for domain info

## Dependencies

```
pytrends       (Google Trends)   pip install pytrends
```

All other features use Python stdlib only (urllib, json, re). No additional packages required.

## References

- [Free APIs Reference](references/free-apis.md) — All free data sources, rate limits, setup instructions
