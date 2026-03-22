# Free SEO Data Sources

Reference for all free (and near-free) data sources used by the seo-freedata skill.

## Completely Free — No Account Required

| Source | Data | Limits |
|--------|------|--------|
| Google Autocomplete | Keyword suggestions, related queries | Unofficial, no published limit |
| RDAP (rdap.org) | WHOIS domain registration data | Unlimited, IANA-backed |
| whoisjsonapi.com | WHOIS with structured JSON | Free tier available |
| HTTP response headers | Server, CDN, X-Powered-By | Unlimited |
| HTML pattern matching | CMS, framework, analytics detection | Unlimited |

## Free With API Key

| Source | Data | Free Limit | Get Key |
|--------|------|-----------|---------|
| **Google PageSpeed Insights** | Core Web Vitals, Lighthouse scores, performance audits | **25,000 requests/day** | console.developers.google.com → Enable PageSpeed Insights API |
| **Google Search Console API** | Your site's keywords, positions, CTR, impressions | Unlimited (own site only) | Same Google account, OAuth setup |

### Setting Up Google API Key (5 minutes)
1. Go to console.developers.google.com
2. Create a project (or use existing)
3. Enable "PageSpeed Insights API"
4. Create credentials → API Key
5. Set env var: `export GOOGLE_API_KEY=your_key_here`

## Cheap Paid (Near-Free)

| Source | Data | Cost | Free Tier |
|--------|------|------|-----------|
| **Serper.dev** | Live Google SERP, PAA, Featured Snippets | $50 / 50k queries | **2,500 searches free on signup** |
| **ScaleSerp** | Google SERP | $0.0025/search | 100/month free |
| **SerpAPI** | Google SERP + shopping + maps | varies | 100/month free |

**Serper.dev is the recommended upgrade path.** At $50/50k queries it's roughly 100x cheaper than DataForSEO for SERP data, and it has Google, YouTube, Images, News, Scholar, and Maps.

### Setting Up Serper.dev
1. Signup at serper.dev (takes 60 seconds, gets you 2,500 free searches)
2. Copy your API key from the dashboard
3. Set env var: `export SERPER_API_KEY=your_key_here`

## What Cannot Be Replicated for Free

These DataForSEO features have no reliable free equivalent:

| Feature | Why No Free Option |
|---------|-------------------|
| Keyword search volume | Google Keyword Planner requires ad spend; all others are estimates |
| Keyword difficulty scores | Requires indexed backlink database |
| Backlink profiles | Requires their own crawl database (Ahrefs, Majestic, Moz all pay for this) |
| Competitor ranked keywords | Requires indexed keyword database |
| Traffic estimation | Estimated from rank × CTR × volume — all require paid data |
| AI mention tracking (LLM) | Requires crawling LLM outputs at scale |

**Practical workaround for keyword volume:** Use pytrends for relative trend direction. Use Google Keyword Planner (free with a Google Ads account, even with $0 spend) for rough volume buckets. For precise volume you need Ahrefs/Semrush/DataForSEO.

## Google Search Console API (Best Free Source for YOUR Site)

If you own the site, Google Search Console is unbeatable — it gives you real Google data:
- Exact keywords you rank for
- Impressions, clicks, CTR, average position
- Page-level breakdown
- Coverage issues (indexed, not indexed, errors)
- Core Web Vitals field data

### Setup
1. Verify site in search.google.com/search-console
2. Go to Google Cloud Console → Enable "Search Console API"
3. Create OAuth 2.0 credentials
4. Use `google-auth` + `google-api-python-client` Python libraries

This replaces the DataForSEO `ranked` and `traffic` commands for sites you own.

## pytrends Notes

pytrends wraps the Google Trends undocumented API. Important caveats:
- Values are **relative (0-100)**, not absolute search volumes
- Rate limited: add delays between requests (2-5 seconds)
- May require a VPN if you get 429s from your IP
- Returns 12 months of weekly data by default

Install: `pip install pytrends`
