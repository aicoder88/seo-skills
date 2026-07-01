#!/usr/bin/env python3
"""
Free SEO Data - No-cost replacement for DataForSEO MCP.

Provides: keyword suggestions, Google Trends, PageSpeed Insights,
SERP scraping, tech stack detection, WHOIS lookup.

API keys (all free tiers):
  GOOGLE_API_KEY      PageSpeed Insights — 25,000 req/day free
                      https://console.developers.google.com/
  SERPER_API_KEY      SERP data — 2,500 free searches on signup
                      https://serper.dev/

  Neither key is required; commands fall back gracefully without them.

Usage:
  python free_seo_data.py <command> [args...]

Commands:
  suggest  <keyword>          Google Autocomplete keyword suggestions
  trends   <keyword>          Google Trends interest over time (12 months)
  psi      <url>              PageSpeed Insights (CWV + Lighthouse)
  serp     <keyword>          Google SERP top 10 (Serper.dev or basic scrape)
  tech     <url>              Tech stack detection from headers + HTML
  whois    <domain>           WHOIS registration data
  intent   <keyword>          Classify search intent from SERP signals
"""

import sys
import json
import os
import re
import ssl
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# Use certifi for SSL if available (needed on macOS Python.org installs)
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get(url, headers=None, timeout=15):
    """Simple HTTP GET returning (status_code, body_str, response_headers)."""
    req = urllib.request.Request(url, headers=headers or {})
    req.add_header('User-Agent',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36')
    try:
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=timeout) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='replace'), {}
    except Exception as e:
        return 0, str(e), {}


def out(data):
    """Print JSON and exit."""
    print(json.dumps(data, indent=2, ensure_ascii=False))


# ─── Command: suggest ────────────────────────────────────────────────────────

def cmd_suggest(keyword):
    """
    Google Autocomplete suggestions — zero API key required.
    Endpoint used by Google's own search box.
    """
    q = urllib.parse.quote(keyword)
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={q}"
    status, body, _ = _get(url)
    if status != 200:
        out({"command": "suggest", "error": f"HTTP {status}", "keyword": keyword})
        return

    try:
        data = json.loads(body)
        suggestions = data[1] if len(data) > 1 else []
    except Exception:
        out({"command": "suggest", "error": "Parse failed", "raw": body[:200]})
        return

    out({
        "command": "suggest",
        "source": "Google Autocomplete (free)",
        "keyword": keyword,
        "suggestions": suggestions,
        "count": len(suggestions),
        "note": "Use these as content topic variations and long-tail keywords."
    })


# ─── Command: trends ─────────────────────────────────────────────────────────

def cmd_trends(keyword):
    """
    Google Trends interest over time via pytrends.
    Falls back to a guidance message if pytrends not installed.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        out({
            "command": "trends",
            "error": "pytrends not installed",
            "fix": "pip install pytrends",
            "keyword": keyword
        })
        return

    try:
        pt = TrendReq(hl='en-US', tz=360)
        pt.build_payload([keyword], cat=0, timeframe='today 12-m', geo='', gprop='')
        df = pt.interest_over_time()

        if df.empty:
            out({"command": "trends", "keyword": keyword, "data": [],
                 "note": "No trend data returned (keyword may be too obscure)."})
            return

        series = [
            {"date": str(d.date()), "interest": int(row[keyword])}
            for d, row in df.iterrows()
            if not row.get("isPartial", False)
        ]

        if not series:
            out({"command": "trends", "keyword": keyword, "data": [],
                 "note": "Only partial data available."})
            return

        avg = sum(r["interest"] for r in series) / len(series)
        recent = series[-4:]  # last ~4 weeks
        recent_avg = sum(r["interest"] for r in recent) / len(recent)
        direction = "rising" if recent_avg > avg * 1.1 else \
                    "falling" if recent_avg < avg * 0.9 else "stable"

        out({
            "command": "trends",
            "source": "Google Trends via pytrends (free)",
            "keyword": keyword,
            "trend_direction": direction,
            "average_interest_12m": round(avg, 1),
            "recent_interest_4w": round(recent_avg, 1),
            "peak": max(series, key=lambda x: x["interest"]),
            "series": series,
            "note": "Interest values are 0-100 relative scores, not absolute search volumes."
        })

    except Exception as e:
        out({"command": "trends", "error": str(e), "keyword": keyword})


# ─── Command: psi ─────────────────────────────────────────────────────────────

def cmd_psi(url):
    """
    Google PageSpeed Insights — 25,000 free requests/day.
    Set GOOGLE_API_KEY env var for authenticated requests.
    Works without a key but rate-limited to ~2 req/min.
    """
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    results = {}

    for strategy in ("mobile", "desktop"):
        params = {
            "url": url,
            "strategy": strategy,
            "category": ["performance", "accessibility", "best-practices", "seo"]
        }
        qs_parts = []
        for k, v in params.items():
            if isinstance(v, list):
                for item in v:
                    qs_parts.append(f"category={urllib.parse.quote(item)}")
            else:
                qs_parts.append(f"{k}={urllib.parse.quote(str(v))}")
        if api_key:
            qs_parts.append(f"key={urllib.parse.quote(api_key)}")

        endpoint = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?" + "&".join(qs_parts)
        status, body, _ = _get(endpoint, timeout=60)

        if status != 200:
            results[strategy] = {"error": f"HTTP {status}"}
            continue

        try:
            data = json.loads(body)
        except Exception:
            results[strategy] = {"error": "Parse failed"}
            continue

        lhr = data.get("lighthouseResult", {})
        cats = lhr.get("categories", {})
        audits = lhr.get("audits", {})

        def score(cat_key):
            c = cats.get(cat_key, {})
            s = c.get("score")
            return round(s * 100) if s is not None else None

        def metric(audit_key, field="displayValue"):
            a = audits.get(audit_key, {})
            return a.get(field) or a.get("displayValue", "N/A")

        # Core Web Vitals
        lcp_val = audits.get("largest-contentful-paint", {}).get("numericValue", 0)
        inp_val = audits.get("total-blocking-time", {}).get("numericValue", 0)  # TBT proxy for INP
        cls_val = audits.get("cumulative-layout-shift", {}).get("numericValue", 0.0)

        def cwv_status(metric_name, val):
            thresholds = {
                "lcp": (2500, 4000),
                "tbt": (200, 600),   # TBT proxy
                "cls": (0.1, 0.25),
            }
            good, poor = thresholds.get(metric_name, (0, 0))
            if val <= good:
                return "good"
            elif val <= poor:
                return "needs-improvement"
            return "poor"

        # Failed audits
        opportunities = []
        for audit_key, audit in audits.items():
            if audit.get("score") is not None and audit.get("score") < 0.9:
                if audit.get("details", {}).get("type") in ("opportunity", "table"):
                    opportunities.append({
                        "id": audit_key,
                        "title": audit.get("title", ""),
                        "description": audit.get("description", "")[:120],
                        "savings_ms": audit.get("details", {}).get("overallSavingsMs")
                    })

        results[strategy] = {
            "scores": {
                "performance": score("performance"),
                "seo": score("seo"),
                "accessibility": score("accessibility"),
                "best_practices": score("best-practices")
            },
            "core_web_vitals": {
                "lcp": {
                    "value": metric("largest-contentful-paint"),
                    "ms": round(lcp_val),
                    "status": cwv_status("lcp", lcp_val)
                },
                "tbt_inp_proxy": {
                    "value": metric("total-blocking-time"),
                    "ms": round(inp_val),
                    "status": cwv_status("tbt", inp_val),
                    "note": "TBT is a lab proxy for INP field data"
                },
                "cls": {
                    "value": metric("cumulative-layout-shift"),
                    "score": round(cls_val, 3),
                    "status": cwv_status("cls", cls_val)
                },
                "fcp": metric("first-contentful-paint"),
                "ttfb": metric("server-response-time")
            },
            "top_opportunities": sorted(
                [o for o in opportunities if o.get("savings_ms")],
                key=lambda x: -(x.get("savings_ms") or 0)
            )[:5]
        }

    out({
        "command": "psi",
        "source": "Google PageSpeed Insights (free — 25k req/day)",
        "url": url,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "authenticated": bool(api_key),
        "mobile": results.get("mobile"),
        "desktop": results.get("desktop"),
        "note": "Set GOOGLE_API_KEY env var for higher rate limits. "
                "Get free key at console.developers.google.com"
    })


# ─── Command: serp ────────────────────────────────────────────────────────────

def cmd_serp(keyword):
    """
    SERP results via Serper.dev (set SERPER_API_KEY env var).
    Serper.dev: 2,500 free searches on signup, then ~$50/50k queries.
    Without a key: falls back to Google Suggest + basic intent signals.
    """
    api_key = os.environ.get("SERPER_API_KEY", "")

    if api_key:
        _serp_serper(keyword, api_key)
    else:
        _serp_fallback(keyword)


def _serp_serper(keyword, api_key):
    """Live SERP via Serper.dev API."""
    payload = json.dumps({"q": keyword, "num": 10}).encode()
    req = urllib.request.Request(
        "https://google.serper.dev/search",
        data=payload,
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        out({"command": "serp", "error": str(e), "keyword": keyword})
        return

    organic = data.get("organic", [])
    paa = data.get("peopleAlsoAsk", [])
    related = data.get("relatedSearches", [])
    featured = data.get("answerBox", None)
    knowledge = data.get("knowledgeGraph", None)

    results = [{
        "position": r.get("position"),
        "title": r.get("title"),
        "url": r.get("link"),
        "domain": urllib.parse.urlparse(r.get("link", "")).netloc,
        "snippet": r.get("snippet"),
        "sitelinks": bool(r.get("sitelinks"))
    } for r in organic[:10]]

    # SERP features present
    features = []
    if featured:
        features.append("featured_snippet")
    if knowledge:
        features.append("knowledge_panel")
    if paa:
        features.append("people_also_ask")
    if any(r.get("position") == 0 for r in organic):
        features.append("position_zero")

    # Intent signal from SERP
    domains = [r["domain"] for r in results]
    titles = " ".join(r.get("title", "") for r in results).lower()
    intent = _classify_intent_from_serp(keyword, titles, results)

    out({
        "command": "serp",
        "source": "Serper.dev (free tier: 2,500 searches on signup)",
        "keyword": keyword,
        "intent": intent,
        "serp_features": features,
        "results": results,
        "people_also_ask": [q.get("question") for q in paa[:5]],
        "related_searches": [r.get("query") for r in related[:8]],
        "competitor_domains": list(dict.fromkeys(domains[:10]))
    })


def _serp_fallback(keyword):
    """No-key fallback: suggestions + intent inference (no live SERP positions)."""
    q = urllib.parse.quote(keyword)

    # Get suggestions (free)
    sug_url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={q}"
    _, sug_body, _ = _get(sug_url)
    try:
        suggestions = json.loads(sug_body)[1]
    except Exception:
        suggestions = []

    intent = _classify_intent_from_keyword(keyword)

    out({
        "command": "serp",
        "source": "Google Suggest fallback (no SERP positions — add SERPER_API_KEY for live rankings)",
        "keyword": keyword,
        "intent": intent,
        "suggestions": suggestions[:10],
        "note": (
            "Live SERP positions require SERPER_API_KEY. "
            "Get 2,500 free searches at serper.dev — signup takes 60 seconds."
        )
    })


# ─── Command: tech ────────────────────────────────────────────────────────────

def cmd_tech(url):
    """
    Tech stack detection from HTTP response headers + HTML patterns.
    No API key required.
    """
    status, body, headers = _get(url)
    if status == 0:
        out({"command": "tech", "error": body, "url": url})
        return

    detected = []

    # Header-based detection
    server = headers.get("Server", headers.get("server", ""))
    if server:
        detected.append({"technology": server, "category": "Web Server", "source": "Server header"})

    x_powered = headers.get("X-Powered-By", headers.get("x-powered-by", ""))
    if x_powered:
        detected.append({"technology": x_powered, "category": "Runtime", "source": "X-Powered-By header"})

    cf = headers.get("CF-Ray", headers.get("cf-ray", ""))
    if cf:
        detected.append({"technology": "Cloudflare", "category": "CDN", "source": "CF-Ray header"})

    via = headers.get("Via", headers.get("via", ""))
    if "varnish" in via.lower():
        detected.append({"technology": "Varnish", "category": "Cache", "source": "Via header"})

    # HTML-based signatures
    patterns = [
        (r'wp-content|wp-includes|wordpress', "WordPress", "CMS"),
        (r'shopify\.com|cdn\.shopify', "Shopify", "E-commerce"),
        (r'squarespace\.com|static\.squarespace', "Squarespace", "Website Builder"),
        (r'wix\.com|wixstatic\.com', "Wix", "Website Builder"),
        (r'ghost\.io|content\/ghost', "Ghost", "CMS"),
        (r'webflow\.com|webflow\.io', "Webflow", "Website Builder"),
        (r'framer\.com|framerusercontent', "Framer", "Website Builder"),
        (r'next\/dist|__NEXT_DATA__', "Next.js", "Framework"),
        (r'nuxt|__nuxt', "Nuxt.js", "Framework"),
        (r'gatsby|gatsby-plugin', "Gatsby", "Framework"),
        (r'astro:root|astro-island', "Astro", "Framework"),
        (r'react\.development|react\.production|__reactFiber', "React", "Frontend Framework"),
        (r'vue\.runtime|vue\.esm|__vue__', "Vue.js", "Frontend Framework"),
        (r'angular\.js|ng-version', "Angular", "Frontend Framework"),
        (r'gtag\(|googletagmanager\.com', "Google Analytics / GTM", "Analytics"),
        (r'plausible\.io', "Plausible", "Analytics"),
        (r'cdn\.segment\.com|analytics\.js', "Segment", "Analytics"),
        (r'hotjar\.com', "Hotjar", "Analytics"),
        (r'intercom\.io|intercomcdn', "Intercom", "Customer Success"),
        (r'stripe\.com\/v3|stripe\.js', "Stripe", "Payments"),
        (r'fastly\.net|fastly-io', "Fastly", "CDN"),
        (r'cloudfront\.net', "AWS CloudFront", "CDN"),
        (r'bunnycdn\.com|b-cdn\.net', "BunnyCDN", "CDN"),
        (r'netlify\.app|netlify\.com', "Netlify", "Hosting"),
        (r'vercel\.app|vercel\.com', "Vercel", "Hosting"),
        (r'pages\.cloudflare\.com', "Cloudflare Pages", "Hosting"),
        (r'tailwind', "Tailwind CSS", "CSS Framework"),
        (r'bootstrap\.min\.css|bootstrap\.bundle', "Bootstrap", "CSS Framework"),
        (r'hubspot|hbspt\.forms', "HubSpot", "CRM/Marketing"),
        (r'salesforce\.com|pardot', "Salesforce", "CRM"),
        (r'schema\.org.*Product|"@type":"Product"', "Product Schema", "Structured Data"),
        (r'schema\.org.*Article|"@type":"Article"', "Article Schema", "Structured Data"),
        (r'schema\.org.*LocalBusiness|"@type":"LocalBusiness"', "LocalBusiness Schema", "Structured Data"),
    ]

    seen = set(t["technology"] for t in detected)
    for pattern, tech, category in patterns:
        if tech not in seen and re.search(pattern, body, re.IGNORECASE):
            detected.append({"technology": tech, "category": category, "source": "HTML pattern"})
            seen.add(tech)

    # Categorize
    by_category = {}
    for item in detected:
        cat = item["category"]
        by_category.setdefault(cat, []).append(item["technology"])

    out({
        "command": "tech",
        "source": "Header + HTML pattern analysis (free)",
        "url": url,
        "http_status": status,
        "technologies_detected": len(detected),
        "by_category": by_category,
        "all": detected,
        "note": "For deeper detection install Wappalyzer CLI: npm i -g wappalyzer"
    })


# ─── Command: whois ───────────────────────────────────────────────────────────

def cmd_whois(domain):
    """
    WHOIS lookup via free public API.
    No API key required.
    """
    domain = domain.replace("https://", "").replace("http://", "").split("/")[0]

    # Use whoisjsonapi.com (free, no auth)
    url = f"https://whoisjsonapi.com/v1/{urllib.parse.quote(domain)}"
    status, body, _ = _get(url)

    if status == 200:
        try:
            data = json.loads(body)
            domain_data = data.get("domain", {})
            out({
                "command": "whois",
                "source": "whoisjsonapi.com (free)",
                "domain": domain,
                "registrar": domain_data.get("registrar", {}).get("name") or data.get("registrar"),
                "created": domain_data.get("created_date") or data.get("created_date"),
                "expires": domain_data.get("expiration_date") or data.get("expiration_date"),
                "updated": domain_data.get("updated_date") or data.get("updated_date"),
                "nameservers": domain_data.get("name_servers", []),
                "status": domain_data.get("status", []),
                "registrant_country": domain_data.get("registrant", {}).get("country"),
                "raw": data
            })
            return
        except Exception:
            pass

    # Fallback: rdap.org (IANA-backed, always free)
    rdap_url = f"https://rdap.org/domain/{urllib.parse.quote(domain)}"
    status2, body2, _ = _get(rdap_url)

    if status2 == 200:
        try:
            data = json.loads(body2)
            events = {e.get("eventAction"): e.get("eventDate")
                      for e in data.get("events", [])}
            ns = [ns.get("ldhName", "") for ns in data.get("nameservers", [])]
            registrar_entities = [
                e.get("vcardArray", [[]])[1]
                for e in data.get("entities", [])
                if "registrar" in e.get("roles", [])
            ]
            registrar_name = None
            if registrar_entities:
                for vcard in registrar_entities[0]:
                    if isinstance(vcard, list) and vcard[0] == "fn":
                        registrar_name = vcard[3]

            out({
                "command": "whois",
                "source": "RDAP via rdap.org (free, IANA-backed)",
                "domain": domain,
                "registrar": registrar_name,
                "created": events.get("registration"),
                "expires": events.get("expiration"),
                "updated": events.get("last changed"),
                "nameservers": ns,
                "status": data.get("status", [])
            })
            return
        except Exception:
            pass

    out({"command": "whois", "error": f"Both WHOIS sources failed (HTTP {status}/{status2})",
         "domain": domain})


# ─── Command: intent ──────────────────────────────────────────────────────────

def cmd_intent(keyword):
    """
    Classify search intent using Google Suggest signals.
    No API key required.
    """
    q = urllib.parse.quote(keyword)
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={q}"
    _, body, _ = _get(url)
    try:
        suggestions = json.loads(body)[1]
    except Exception:
        suggestions = []

    intent = _classify_intent_from_keyword(keyword)
    signals = _intent_signals(keyword, suggestions)

    out({
        "command": "intent",
        "source": "Keyword pattern + Suggest analysis (free)",
        "keyword": keyword,
        "primary_intent": intent["type"],
        "confidence": intent["confidence"],
        "content_type_recommendation": intent["content_type"],
        "signals": signals,
        "related_suggestions": suggestions[:8],
        "note": "Add SERPER_API_KEY for SERP-verified intent classification."
    })


# ─── Intent classification helpers ───────────────────────────────────────────

def _classify_intent_from_keyword(keyword):
    kw = keyword.lower()
    transactional = ["buy", "purchase", "order", "price", "pricing", "cost", "cheap",
                     "deal", "discount", "coupon", "shop", "sale", "hire", "get", "download",
                     "subscribe", "sign up", "register", "trial", "free trial"]
    commercial = ["best", "top", "review", "reviews", "vs", "versus", "compare",
                  "comparison", "alternative", "alternatives", "recommend", "rated",
                  "ranking", "ranked", "worth it", "pros and cons"]
    informational = ["how", "what", "why", "when", "where", "who", "which",
                     "does", "can", "is", "are", "guide", "tutorial", "learn",
                     "explain", "definition", "meaning", "example", "examples"]
    navigational = ["login", "sign in", "account", "dashboard", "portal", "official",
                    "website", "site", "contact", "support", "help"]

    scores = {"transactional": 0, "commercial": 0, "informational": 0, "navigational": 0}
    for word in transactional:
        if word in kw:
            scores["transactional"] += 2
    for word in commercial:
        if word in kw:
            scores["commercial"] += 2
    for word in informational:
        if word in kw:
            scores["informational"] += 2
    for word in navigational:
        if word in kw:
            scores["navigational"] += 2

    content_map = {
        "transactional": "Product page, landing page, or pricing page",
        "commercial": "Comparison article, review, or 'best X' listicle",
        "informational": "Blog post, guide, tutorial, or FAQ page",
        "navigational": "Brand/homepage or direct navigation page"
    }

    best = max(scores, key=lambda k: scores[k])
    confidence = "high" if scores[best] >= 4 else "medium" if scores[best] >= 2 else "low"

    return {
        "type": best,
        "confidence": confidence,
        "content_type": content_map[best],
        "scores": scores
    }


def _classify_intent_from_serp(keyword, titles, results):
    """Refine intent using SERP data (when available)."""
    base = _classify_intent_from_keyword(keyword)

    # Check result types
    domains = [r.get("domain", "") for r in results]
    ecommerce_signals = sum(1 for d in domains if any(
        x in d for x in ["amazon", "etsy", "ebay", "shopify", "store", "shop"]))

    if ecommerce_signals >= 3:
        base["type"] = "transactional"
        base["confidence"] = "high"

    return base


def _intent_signals(keyword, suggestions):
    signals = []
    kw = keyword.lower()
    sug_text = " ".join(suggestions).lower()

    if any(w in kw for w in ["how to", "what is", "guide", "tutorial"]):
        signals.append("Informational pattern in keyword")
    if any(w in kw for w in ["best", "top", "vs", "review"]):
        signals.append("Commercial investigation pattern")
    if any(w in kw for w in ["buy", "price", "cost", "cheap"]):
        signals.append("Transactional intent signal")
    if any(w in sug_text for w in ["how", "what", "why", "guide"]):
        signals.append("Informational suggestions from Google")
    if any(w in sug_text for w in ["best", "review", "vs", "alternative"]):
        signals.append("Commercial suggestions from Google")

    return signals if signals else ["No strong intent signals — mixed or generic keyword"]


# ─── CLI entry point ─────────────────────────────────────────────────────────

COMMANDS = {
    "suggest": (cmd_suggest, "<keyword>"),
    "trends":  (cmd_trends,  "<keyword>"),
    "psi":     (cmd_psi,     "<url>"),
    "serp":    (cmd_serp,    "<keyword>"),
    "tech":    (cmd_tech,    "<url>"),
    "whois":   (cmd_whois,   "<domain>"),
    "intent":  (cmd_intent,  "<keyword>"),
}


def main():
    if len(sys.argv) < 3:
        print("Usage: python free_seo_data.py <command> <argument>")
        print("\nCommands:")
        for cmd, (_, hint) in COMMANDS.items():
            print(f"  {cmd:<10} {hint}")
        print("\nOptional env vars (all free tiers):")
        print("  GOOGLE_API_KEY   PageSpeed Insights (25k req/day free)")
        print("  SERPER_API_KEY   SERP data (2,500 free searches on signup)")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    arg = " ".join(sys.argv[2:])

    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(COMMANDS)}")
        sys.exit(1)

    fn, _ = COMMANDS[cmd]
    fn(arg)


if __name__ == "__main__":
    main()
