"""
MCA21 Data Fetcher - Session-based approach
Uses requests with proper session handling, cookies, and headers.
Also checks for alternative data download endpoints.
"""

import requests
import json
import os
import re
from datetime import datetime

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "mca21_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TARGETS = [
    {
        "name": "disqualified_directors",
        "url": "https://www.mca.gov.in/content/mca/global/en/data-and-reports/rd-roc-info/disqualified-directors.html",
        "description": "Directors disqualified u/s 164(2)(a)",
    },
    {
        "name": "defaulter_companies",
        "url": "https://www.mca.gov.in/content/mca/global/en/data-and-reports/company-llp-info/under-alert/defaulter-companies.html",
        "description": "Companies flagged as defaulters",
    },
    {
        "name": "defaulter_directors",
        "url": "https://www.mca.gov.in/content/mca/global/en/data-and-reports/company-llp-info/under-alert/defaulter-directors.html",
        "description": "Directors flagged as defaulters",
    },
    {
        "name": "strike_off_companies",
        "url": "https://www.mca.gov.in/content/mca/global/en/data-and-reports/company-llp-info/under-alert/companies-under-strike-off.html",
        "description": "Companies under strike off",
    },
    {
        "name": "vanishing_companies",
        "url": "https://www.mca.gov.in/content/mca/global/en/data-and-reports/company-llp-info/under-alert/vanishing-companies.html",
        "description": "Vanishing companies",
    },
    {
        "name": "dormant_companies",
        "url": "https://www.mca.gov.in/content/mca/global/en/data-and-reports/company-llp-info/under-alert/dormant-companies.html",
        "description": "Dormant companies",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


def analyze_html(html, name):
    """Analyze HTML content for data structures."""
    result = {
        "name": name,
        "html_length": len(html),
        "has_tables": "<table" in html.lower(),
        "has_pdf_links": ".pdf" in html.lower(),
        "has_forms": "<form" in html.lower(),
        "has_iframe": "<iframe" in html.lower(),
        "has_json_data": False,
        "pdf_urls": [],
        "api_endpoints": [],
        "form_actions": [],
        "data_patterns": [],
    }
    
    # Find PDF links
    pdf_pattern = re.compile(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', re.IGNORECASE)
    result["pdf_urls"] = pdf_pattern.findall(html)
    
    # Find API endpoints in scripts
    api_pattern = re.compile(r'(?:fetch|axios|ajax|XMLHttpRequest|url)["\s:=]+["\']([^"\']*(?:api|data|json|search|query)[^"\']*)["\']', re.IGNORECASE)
    result["api_endpoints"] = api_pattern.findall(html)
    
    # Find form actions
    form_pattern = re.compile(r'action=["\']([^"\']*)["\']', re.IGNORECASE)
    result["form_actions"] = form_pattern.findall(html)
    
    # Check for JSON data in script tags
    json_pattern = re.compile(r'(?:var|let|const)\s+\w+\s*=\s*(\{[^}]+\}|\[[^\]]+\])', re.IGNORECASE)
    json_matches = json_pattern.findall(html)
    if json_matches:
        result["has_json_data"] = True
        result["data_patterns"] = [m[:200] for m in json_matches[:5]]
    
    # Extract title
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    if title_match:
        result["title"] = title_match.group(1).strip()
    
    # Extract h1
    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
    if h1_match:
        result["h1"] = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()
    
    # Check for AEM component data
    aem_pattern = re.compile(r'data-sly-(?:use|test|list|include|resource)', re.IGNORECASE)
    result["aem_components"] = len(aem_pattern.findall(html))
    
    # Look for XHR/fetch URLs in scripts
    xhr_pattern = re.compile(r'(?:\.open|fetch)\s*\(\s*["\']([A-Z]+)["\']\s*,\s*["\']([^"\']+)["\']', re.IGNORECASE)
    xhr_matches = xhr_pattern.findall(html)
    result["xhr_endpoints"] = [{"method": m[0], "url": m[1]} for m in xhr_matches]
    
    return result


def try_fetch(session, url, name):
    """Try to fetch a page and analyze the response."""
    print(f"\n{'='*80}")
    print(f"FETCHING: {name}")
    print(f"URL: {url}")
    print(f"{'='*80}")
    
    try:
        # First, get the homepage to establish cookies
        resp = session.get("https://www.mca.gov.in/content/mca/global/en/home.html", 
                          headers=HEADERS, timeout=30)
        print(f"  Homepage: {resp.status_code}, cookies: {len(session.cookies)}")
        
        # Now try the target page
        resp = session.get(url, headers=HEADERS, timeout=30)
        print(f"  Target page: {resp.status_code}")
        print(f"  Content-Type: {resp.headers.get('content-type', 'N/A')}")
        print(f"  Content-Length: {len(resp.text)}")
        
        if resp.status_code == 200:
            analysis = analyze_html(resp.text, name)
            print(f"  Title: {analysis.get('title', 'N/A')}")
            print(f"  H1: {analysis.get('h1', 'N/A')}")
            print(f"  Has tables: {analysis['has_tables']}")
            print(f"  Has PDF links: {analysis['has_pdf_links']}")
            print(f"  PDF URLs found: {len(analysis['pdf_urls'])}")
            for pdf in analysis['pdf_urls'][:10]:
                print(f"    - {pdf[:120]}")
            print(f"  Has forms: {analysis['has_forms']}")
            print(f"  Form actions: {analysis['form_actions']}")
            print(f"  XHR endpoints: {analysis['xhr_endpoints']}")
            print(f"  AEM components: {analysis['aem_components']}")
            print(f"  Has JSON data: {analysis['has_json_data']}")
            if analysis['data_patterns']:
                print(f"  Data patterns: {analysis['data_patterns'][:2]}")
            
            # Save HTML for manual inspection
            html_file = os.path.join(OUTPUT_DIR, f"{name}.html")
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(resp.text)
            print(f"  HTML saved to: {html_file}")
            
            return analysis
        else:
            print(f"  FAILED with status {resp.status_code}")
            print(f"  Response headers: {dict(resp.headers)}")
            print(f"  Response body preview: {resp.text[:500]}")
            return {"error": f"HTTP {resp.status_code}", "status": resp.status_code}
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return {"error": str(e)}


def check_alternative_endpoints():
    """Check for alternative data download endpoints on MCA21."""
    print("\n" + "="*80)
    print("CHECKING ALTERNATIVE DATA ENDPOINTS")
    print("="*80)
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # Check various data endpoints
    alt_urls = [
        # XBRL data downloads
        "https://www.mca.gov.in/content/mca/global/en/data-and-reports/company-llp-info.html",
        # Monthly data
        "https://www.mca.gov.in/content/mca/global/en/data-and-reports/company-llp-info/incorporated-closed-month.html",
        # CSR data
        "https://www.mca.gov.in/content/mca/global/en/data-and-reports/company-llp-info/csr-data-summary.html",
        # Data & Reports main
        "https://www.mca.gov.in/content/mca/global/en/data-and-reports.html",
        # ROC info
        "https://www.mca.gov.in/content/mca/global/en/data-and-reports/rd-roc-info.html",
        # Companies struck off
        "https://www.mca.gov.in/content/mca/global/en/data-and-reports/rd-roc-info/companies-struck-roc.html",
        # Disqualified directors (ROC version)
        "https://www.mca.gov.in/content/mca/global/en/data-and-reports/rd-roc-info/disqualified-directors.html",
        # Master data service
        "https://www.mca.gov.in/content/mca/global/en/mca/master-data/MDS.html",
        # Find CIN
        "https://www.mca.gov.in/content/mca/global/en/mca/fo-llp-services/findCinFinalSingleCom.html",
        # Check annual filing status
        "https://www.mca.gov.in/content/mca/global/en/mca/fo-llp-services/check-annual-filing-status.html",
        # IEPF search
        "https://www.mca.gov.in/content/mca/global/en/mca/iepf-related-services/search-unclaimed-unpaid-amount-shares.html",
        # View public documents
        "https://www.mca.gov.in/content/mca/global/en/mca/document-related-services/view-public-documents-v3/view-public-documents.html",
    ]
    
    results = {}
    for url in alt_urls:
        try:
            # Try homepage first for cookies
            session.get("https://www.mca.gov.in/content/mca/global/en/home.html", timeout=15)
            
            resp = session.get(url, timeout=15)
            name = url.split("/")[-1].replace(".html", "")
            print(f"\n  {name}: {resp.status_code} ({len(resp.text)} bytes)")
            
            if resp.status_code == 200:
                analysis = analyze_html(resp.text, name)
                if analysis['pdf_urls']:
                    print(f"    PDFs: {len(analysis['pdf_urls'])}")
                    for pdf in analysis['pdf_urls'][:3]:
                        print(f"      - {pdf[:100]}")
                if analysis['xhr_endpoints']:
                    print(f"    XHR: {analysis['xhr_endpoints']}")
                if analysis['has_tables']:
                    print(f"    Has tables: YES")
                results[name] = analysis
            else:
                results[name] = {"status": resp.status_code}
                
        except Exception as e:
            print(f"  {url.split('/')[-1]}: ERROR - {e}")
            results[url.split("/")[-1]] = {"error": str(e)}
    
    return results


def main():
    print("MCA21 Data Fetcher - Session-based Approach")
    print(f"Output: {OUTPUT_DIR}")
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # Fetch all target pages
    all_results = {}
    for target in TARGETS:
        result = try_fetch(session, target["url"], target["name"])
        all_results[target["name"]] = result
    
    # Check alternative endpoints
    alt_results = check_alternative_endpoints()
    
    # Save all results
    output = {
        "scraped_at": datetime.now().isoformat(),
        "main_results": all_results,
        "alternative_endpoints": alt_results,
    }
    
    output_file = os.path.join(OUTPUT_DIR, "session_fetch_results.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
