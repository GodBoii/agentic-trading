"""
MCA21 Tier 1 Data Scraper - Test Run
Scrapes public alert lists from MCA21 to analyze data structure and usefulness.
"""

import asyncio
import json
import os
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


async def scrape_page(page, target, network_requests):
    """Scrape a single MCA21 page and extract all available data."""
    name = target["name"]
    url = target["url"]
    print(f"\n{'='*80}")
    print(f"SCRAPING: {target['description']}")
    print(f"URL: {url}")
    print(f"{'='*80}")

    try:
        response = await page.goto(url, wait_until="networkidle", timeout=60000)
        print(f"  Page loaded. Status: {response.status}")

        # Wait extra time for dynamic content
        await page.wait_for_timeout(5000)

        # Capture all network requests made for this page
        page_requests = [r for r in network_requests if url.split("/")[-1] in r.get("url", "") or "mca" in r.get("url", "").lower()]
        
        # Also look for any API/XHR requests
        api_requests = [r for r in network_requests if r.get("type") in ("xhr", "fetch", "json")]
        
        print(f"\n  Network requests captured: {len(network_requests)}")
        print(f"  API/XHR requests: {len(api_requests)}")
        for req in api_requests:
            print(f"    - [{req.get('method', 'GET')}] {req.get('url', 'unknown')[:120]}")

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
            };

            // Get H1
            const h1 = document.querySelector('h1');
            if (h1) result.h1 = h1.innerText.trim();

            // Get all tables
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

            // Get PDF links
            document.querySelectorAll('a[href*=".pdf"]').forEach(a => {
                result.pdfLinks.push({
                    text: a.innerText.trim(),
                    href: a.href,
                });
            });

            // Get download links (any link with download-related text or href)
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

            // Get form elements
            document.querySelectorAll('form, input, select, button[type="submit"]').forEach(el => {
                result.formElements.push({
                    tag: el.tagName,
                    type: el.type || '',
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.placeholder || '',
                    value: el.value || '',
                });
            });

            // Get main content area text
            const mainContent = document.querySelector('.component-content, .aem-GridColumn, main, #content, .page-content');
            if (mainContent) {
                result.mainContent = mainContent.innerText.substring(0, 5000);
            }

            // Get all links with text
            document.querySelectorAll('a[href]').forEach(a => {
                const text = a.innerText.trim();
                if (text && text.length > 2) {
                    result.allLinks.push({
                        text: text.substring(0, 200),
                        href: a.href,
                    });
                }
            });

            // Check for iframes
            document.querySelectorAll('iframe').forEach(iframe => {
                result.iframes.push({
                    src: iframe.src,
                    id: iframe.id,
                });
            });

            return result;
        }""")

        # Print extracted data summary
        print(f"\n  Page title: {data.get('title', 'N/A')}")
        print(f"  H1: {data.get('h1', 'N/A')}")
        print(f"  Tables found: {len(data.get('tables', []))}")
        for i, table in enumerate(data.get('tables', [])):
            print(f"    Table {i}: {table['rowCount']} rows, headers: {table['headers'][:5]}")
            if table['sampleRows']:
                print(f"    Sample row: {table['sampleRows'][0][:5]}...")
        
        print(f"  PDF links: {len(data.get('pdfLinks', []))}")
        for pdf in data.get('pdfLinks', [])[:5]:
            print(f"    - {pdf['text'][:80]} -> {pdf['href'][:100]}")
        
        print(f"  Download links: {len(data.get('downloadLinks', []))}")
        for dl in data.get('downloadLinks', [])[:5]:
            print(f"    - {dl['text'][:80]} -> {dl['href'][:100]}")
        
        print(f"  Form elements: {len(data.get('formElements', []))}")
        print(f"  Total links: {len(data.get('allLinks', []))}")
        print(f"  Iframes: {len(data.get('iframes', []))}")

        if data.get('mainContent'):
            print(f"\n  Main content preview (first 1000 chars):")
            print(f"  {data['mainContent'][:1000]}")

        # Save full data
        output_file = os.path.join(OUTPUT_DIR, f"{name}.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({
                "target": target,
                "scraped_at": datetime.now().isoformat(),
                "data": data,
                "api_requests": api_requests,
            }, f, indent=2, ensure_ascii=False)
        print(f"\n  Saved to: {output_file}")

        return data

    except Exception as e:
        print(f"  ERROR: {e}")
        return None


async def main():
    print("MCA21 Tier 1 Scraper - Test Run")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Targets: {len(TARGETS)} pages")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        all_results = {}
        
        for target in TARGETS:
            network_requests = []
            
            # Set up network request interception
            async def on_request(request):
                network_requests.append({
                    "url": request.url,
                    "method": request.method,
                    "type": request.resource_type,
                    "headers": dict(request.headers) if request.headers else {},
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

            # Remove listeners for next iteration
            page.remove_listener("request", on_request)
            page.remove_listener("response", on_response)
            
            # Small delay between pages
            await page.wait_for_timeout(2000)

        await browser.close()

    # Save summary
    summary = {
        "scraped_at": datetime.now().isoformat(),
        "targets_scraped": len(all_results),
        "results": {},
    }
    for name, data in all_results.items():
        if data:
            summary["results"][name] = {
                "tables": len(data.get("tables", [])),
                "pdf_links": len(data.get("pdfLinks", [])),
                "download_links": len(data.get("downloadLinks", [])),
                "total_links": len(data.get("allLinks", [])),
                "has_form": len(data.get("formElements", [])) > 0,
                "main_content_length": len(data.get("mainContent", "")),
            }
    
    summary_file = os.path.join(OUTPUT_DIR, "scrape_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\n\nSummary saved to: {summary_file}")
    print("DONE!")


if __name__ == "__main__":
    asyncio.run(main())
