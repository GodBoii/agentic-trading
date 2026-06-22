"""
MCA21 Tier 1 Scraper - Stealth Mode
Uses stealth techniques to bypass bot detection.
Also tries to find the underlying data API endpoints.
"""

import asyncio
import json
import os
import re
from datetime import datetime
from playwright.async_api import async_playwright

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


async def apply_stealth(page):
    """Apply stealth techniques to avoid bot detection."""
    await page.add_init_script("""
        // Override webdriver property
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Override plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        
        // Override languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        
        // Override platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32'
        });
        
        // Override Chrome runtime
        window.chrome = {
            runtime: {},
        };
        
        // Override permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // Override WebGL vendor and renderer
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            if (parameter === 37446) {
                return 'Intel Iris OpenGL Engine';
            }
            return getParameter.call(this, parameter);
        };
    """)


async def scrape_page(page, target, network_requests):
    """Scrape a single MCA21 page."""
    name = target["name"]
    url = target["url"]
    print(f"\n{'='*80}")
    print(f"SCRAPING: {target['description']}")
    print(f"URL: {url}")
    print(f"{'='*80}")

    try:
        response = await page.goto(url, wait_until="networkidle", timeout=60000)
        status = response.status
        print(f"  Page loaded. Status: {status}")
        
        if status == 403:
            print("  BLOCKED (403). Trying alternative approach...")
            # Try fetching via the AEM content endpoint
            # MCA21 uses AEM - try the .json endpoint
            json_url = url.replace(".html", ".json")
            print(f"  Trying JSON endpoint: {json_url}")
            resp2 = await page.goto(json_url, wait_until="networkidle", timeout=30000)
            status2 = resp2.status
            print(f"  JSON endpoint status: {status2}")
            if status2 == 200:
                body = await resp2.text()
                print(f"  JSON response length: {len(body)}")
                print(f"  JSON preview: {body[:500]}")
                return {"raw_json": body[:10000], "status": status2}

            # Try .model.json (AEM Sling Model)
            model_url = url.replace(".html", ".model.json")
            print(f"  Trying AEM Model endpoint: {model_url}")
            resp3 = await page.goto(model_url, wait_until="networkidle", timeout=30000)
            status3 = resp3.status
            print(f"  AEM Model status: {status3}")
            if status3 == 200:
                body = await resp3.text()
                print(f"  Model response length: {len(body)}")
                print(f"  Model preview: {body[:500]}")
                return {"raw_json": body[:10000], "status": status3}

            return {"error": "Access Denied", "status": status}

        # Wait for dynamic content
        await page.wait_for_timeout(5000)

        # Extract page content
        data = await page.evaluate("""() => {
            const result = {
                title: document.title,
                h1: '',
                tables: [],
                pdfLinks: [],
                downloadLinks: [],
                formElements: [],
                mainContent: '',
                allLinks: [],
                iframes: [],
                scripts: [],
            };

            const h1 = document.querySelector('h1');
            if (h1) result.h1 = h1.innerText.trim();

            const tables = document.querySelectorAll('table');
            tables.forEach((table, idx) => {
                const rows = [];
                table.querySelectorAll('tr').forEach(tr => {
                    const cells = [];
                    tr.querySelectorAll('th, td').forEach(cell => {
                        cells.push(cell.innerText.trim());
                    });
                    if (cells.length > 0) rows.push(cells);
                });
                if (rows.length > 0) {
                    result.tables.push({
                        index: idx,
                        rowCount: rows.length,
                        headers: rows[0] || [],
                        sampleRows: rows.slice(0, 10),
                        allRows: rows,
                    });
                }
            });

            document.querySelectorAll('a[href*=".pdf"]').forEach(a => {
                result.pdfLinks.push({
                    text: a.innerText.trim(),
                    href: a.href,
                });
            });

            document.querySelectorAll('a').forEach(a => {
                const href = a.href || '';
                const text = a.innerText.trim().toLowerCase();
                if (href.includes('.pdf') || href.includes('.zip') || href.includes('.csv') || 
                    href.includes('.xlsx') || href.includes('.xls') || href.includes('download') ||
                    text.includes('download') || text.includes('pdf') || text.includes('click here')) {
                    result.downloadLinks.push({
                        text: a.innerText.trim(),
                        href: a.href,
                    });
                }
            });

            document.querySelectorAll('form, input, select, button[type="submit"]').forEach(el => {
                result.formElements.push({
                    tag: el.tagName,
                    type: el.type || '',
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.placeholder || '',
                });
            });

            const mainContent = document.querySelector('.component-content, .aem-GridColumn, main, #content, .page-content');
            if (mainContent) {
                result.mainContent = mainContent.innerText.substring(0, 5000);
            }

            document.querySelectorAll('a[href]').forEach(a => {
                const text = a.innerText.trim();
                if (text && text.length > 2) {
                    result.allLinks.push({
                        text: text.substring(0, 200),
                        href: a.href,
                    });
                }
            });

            return result;
        }""")

        print(f"\n  Page title: {data.get('title', 'N/A')}")
        print(f"  H1: {data.get('h1', 'N/A')}")
        print(f"  Tables: {len(data.get('tables', []))}")
        for t in data.get('tables', []):
            print(f"    Table: {t['rowCount']} rows, headers: {t['headers'][:5]}")
        print(f"  PDF links: {len(data.get('pdfLinks', []))}")
        for pdf in data.get('pdfLinks', [])[:5]:
            print(f"    - {pdf['text'][:80]}")
            print(f"      {pdf['href'][:120]}")
        print(f"  Download links: {len(data.get('downloadLinks', []))}")
        print(f"  Total links: {len(data.get('allLinks', []))}")

        if data.get('mainContent'):
            print(f"\n  Main content preview:")
            print(f"  {data['mainContent'][:1500]}")

        # Check for API requests
        api_reqs = [r for r in network_requests if r.get("type") in ("xhr", "fetch", "api_response")]
        if api_reqs:
            print(f"\n  API/XHR requests intercepted:")
            for req in api_reqs:
                print(f"    [{req.get('method', '?')}] {req.get('url', '?')[:120]}")
                if req.get('body_preview'):
                    print(f"      Body preview: {req['body_preview'][:300]}")

        return data

    except Exception as e:
        print(f"  ERROR: {e}")
        return {"error": str(e)}


async def main():
    print("MCA21 Tier 1 Scraper - Stealth Mode")
    print(f"Output: {OUTPUT_DIR}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="Asia/Kolkata",
        )
        page = await context.new_page()
        await apply_stealth(page)

        all_results = {}
        
        for target in TARGETS:
            network_requests = []
            
            async def on_request(request):
                network_requests.append({
                    "url": request.url,
                    "method": request.method,
                    "type": request.resource_type,
                })
            
            async def on_response(response):
                url = response.url
                if "mca.gov.in" in url and not url.endswith(('.css', '.js', '.png', '.jpg', '.svg', '.woff', '.woff2', '.ico')):
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type or "xml" in content_type:
                        try:
                            body = await response.text()
                            network_requests.append({
                                "url": url,
                                "method": "RESPONSE",
                                "type": "api_response",
                                "content_type": content_type,
                                "body_preview": body[:2000] if body else "",
                                "status": response.status,
                            })
                        except:
                            pass

            page.on("request", on_request)
            page.on("response", on_response)

            data = await scrape_page(page, target, network_requests)
            all_results[target["name"]] = data

            page.remove_listener("request", on_request)
            page.remove_listener("response", on_response)
            
            await page.wait_for_timeout(2000)

        await browser.close()

    # Save all results
    output_file = os.path.join(OUTPUT_DIR, "scrape_results.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n\nAll results saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
