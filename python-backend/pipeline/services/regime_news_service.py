from __future__ import annotations

from datetime import datetime, timezone
import html
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import requests

from pipeline.config import PipelineConfig
from pipeline.services.market_time_service import MarketTimeService


class RegimeNewsService:
    """
    Collects and normalizes market-context disclosure/news inputs for the regime lane.

    This class owns exchange-side collection, Kotak market-context collection,
    and deterministic fallback analysis.
    The Agno agent runtime is deliberately kept outside this file so the regime
    orchestrator can run the logic branch and the LLM branch as peers.
    """

    BSE_MOBILE_CORPORATES_URL = "https://m.bseindia.com/corporates.aspx"
    BSE_MOBILE_BASE_URL = "https://m.bseindia.com/"
    KOTAK_FII_DII_URL = "https://www.kotakneo.com/share-market-today/fii-dii-data/"
    KOTAK_NEWS_URL = "https://www.kotakneo.com/news/"
    ANALYSIS_SCOPE = "market_context_sources"
    BSE_ANALYSIS_SCOPE = ANALYSIS_SCOPE

    def __init__(self, config: PipelineConfig, market_time: MarketTimeService):
        self.config = config
        self.market_time = market_time
        self.timeout_seconds = float(os.getenv("REGIME_NEWS_HTTP_TIMEOUT_SECONDS", "8"))
        self.max_headlines = int(os.getenv("REGIME_NEWS_MAX_HEADLINES", "40"))
        self.max_detail_fetch = int(os.getenv("REGIME_NEWS_MAX_DETAIL_FETCH", "8"))
        self.session = requests.Session()
        self.section_weights: Dict[str, float] = {
            "corporate_announcements": 1.00,
            "forthcoming_results": 0.55,
            "corporate_actions": 0.45,
            "offers": 0.35,
            "listing": 0.25,
        }

    def collect_market_news_payload(self) -> Dict[str, Any]:
        fetched, source_status = self._fetch_headlines()
        kotak_news = self._fetch_kotak_news(source_status)
        fii_dii = self._fetch_fii_dii_flow(source_status)
        enriched = self._enrich_bse_announcement_details(fetched)
        combined = enriched + kotak_news
        if fii_dii:
            combined.append(self._flow_payload_to_headline(fii_dii))
        deduped = self._deduplicate_headlines(combined)
        prioritized = self._prioritize_headlines(deduped)
        sliced = prioritized[: self.max_headlines]
        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "analysis_scope": self.ANALYSIS_SCOPE,
            "headline_count": len(sliced),
            "headlines": sliced,
            "institutional_flows": fii_dii,
            "source_status": source_status,
            "market_signal_distribution": self._build_section_distribution(sliced),
        }

    def finalize_market_news_payload(
        self,
        collected: Dict[str, Any],
        analysis: Dict[str, Any],
        analysis_engine: str,
        agno_error: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = dict(collected)
        payload.update(
            {
                "analysis_engine": analysis_engine,
                "event_severity_score": float(analysis.get("event_severity_score", 0.0) or 0.0),
                "market_sentiment": analysis.get("market_sentiment", "neutral"),
                "confidence_score": float(analysis.get("confidence_score", 0.0) or 0.0),
                "risk_of_abnormal_volatility": analysis.get("risk_of_abnormal_volatility", "medium"),
                "affected_sectors": analysis.get("affected_sectors", []),
                "event_clusters": analysis.get("event_clusters", []),
                "headline_summary": analysis.get("headline_summary", ""),
                "structured_reasoning": analysis.get("structured_reasoning", ""),
                "birds_eye_view": analysis.get("birds_eye_view", {}),
                "llm_markdown_analysis": analysis.get("llm_markdown_analysis", ""),
                "institutional_flows": collected.get("institutional_flows", {}),
            }
        )
        if agno_error:
            payload["agno_error"] = agno_error
        return payload

    def analyze_with_heuristics(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not rows:
            return {
                "analysis_scope": self.BSE_ANALYSIS_SCOPE,
                "market_sentiment": "neutral",
                "event_severity_score": 0.0,
                "confidence_score": 0.0,
                "risk_of_abnormal_volatility": "medium",
                "affected_sectors": [],
                "event_clusters": [],
                "headline_summary": "No supplied market-context disclosures or news items were available this cycle.",
                "structured_reasoning": "Heuristic mode used because no market-context feed items were available.",
                "birds_eye_view": {
                    "scope": "mixed",
                    "impact_horizon": "unclear",
                    "summary": "No current BSE disclosure context available.",
                },
            }

        positive_terms = {"rally", "surge", "gain", "strong", "beats", "approval", "record high", "dividend"}
        negative_terms = {"fall", "selloff", "decline", "fraud", "loss", "misses", "default", "downgrade"}
        severe_terms = {"fraud", "default", "downgrade", "court", "ban", "probe", "search", "seizure"}
        sector_terms = {
            "bank": "banking",
            "finance": "financials",
            "it": "it",
            "pharma": "pharma",
            "auto": "auto",
            "metal": "metals",
            "energy": "energy",
            "realty": "realty",
            "fmcg": "fmcg",
            "cement": "infrastructure",
            "oil": "energy",
        }

        pos_hits = 0
        neg_hits = 0
        severe_hits = 0
        sector_hits: Dict[str, int] = {}
        section_hits: Dict[str, int] = {}

        for row in rows:
            blob = f"{row.get('title', '')} {row.get('detail_text', '')}".lower()
            section = str(row.get("section") or "unknown")
            section_hits[section] = section_hits.get(section, 0) + 1
            if row.get("source") == "kotak_fii_dii":
                net_flow = self._coerce_float(row.get("net_fii_dii_cash_cr"))
                fii_net = self._coerce_float(row.get("fii_net_cash_cr"))
                if fii_net is not None and fii_net < -3000:
                    neg_hits += 1
                elif fii_net is not None and fii_net > 3000:
                    pos_hits += 1
                if net_flow is not None and abs(net_flow) >= 5000:
                    severe_hits += 1
            for term in positive_terms:
                if term in blob:
                    pos_hits += 1
            for term in negative_terms:
                if term in blob:
                    neg_hits += 1
            for term in severe_terms:
                if re.search(rf"\b{re.escape(term)}\b", blob):
                    severe_hits += 1
            for term, sector_name in sector_terms.items():
                if re.search(rf"\b{re.escape(term)}\b", blob):
                    sector_hits[sector_name] = sector_hits.get(sector_name, 0) + 1

        if pos_hits > neg_hits * 1.2:
            sentiment = "bullish"
        elif neg_hits > pos_hits * 1.2:
            sentiment = "bearish"
        elif pos_hits > 0 or neg_hits > 0:
            sentiment = "mixed"
        else:
            sentiment = "neutral"

        density_base = max(1, min(len(rows), 20))
        active_sections = sum(1 for count in section_hits.values() if count > 0)
        breadth_bonus = 0.0
        if active_sections >= 3:
            breadth_bonus += 0.08
        if section_hits.get("corporate_announcements", 0) >= 10:
            breadth_bonus += 0.05
        severity = min(1.0, (severe_hits / density_base) + breadth_bonus)
        confidence = min(0.9, 0.25 + (min(len(rows), 20) * 0.03))

        if severity >= 0.66:
            risk = "high"
        elif severity >= 0.33:
            risk = "medium"
        else:
            risk = "low"

        top_sectors = sorted(sector_hits.items(), key=lambda item: item[1], reverse=True)
        affected = [name for name, _ in top_sectors[:6]]
        top_sections = sorted(section_hits.items(), key=lambda item: item[1], reverse=True)
        event_clusters = [name for name, _ in top_sections[:4]]

        scope = "isolated"
        if len(affected) >= 3:
            scope = "sectoral"
        if active_sections >= 3 and len(affected) >= 4:
            scope = "broad"
        elif sentiment == "mixed":
            scope = "mixed"

        impact_horizon = "unclear"
        if severity >= 0.7:
            impact_horizon = "immediate_intraday"
        elif severity >= 0.4:
            impact_horizon = "same_day"

        summary = self._heuristic_summary(rows, sentiment, severity)
        reasoning = (
            f"Heuristic aggregation over {len(rows)} supplied market-context items. "
            f"positive_hits={pos_hits}, negative_hits={neg_hits}, severe_hits={severe_hits}, "
            f"sentiment={sentiment}, severity={round(severity, 3)}."
        )

        return {
            "analysis_scope": self.ANALYSIS_SCOPE,
            "market_sentiment": sentiment,
            "event_severity_score": round(severity, 4),
            "confidence_score": round(confidence, 4),
            "risk_of_abnormal_volatility": risk,
            "affected_sectors": affected,
            "event_clusters": event_clusters,
            "headline_summary": summary,
            "structured_reasoning": reasoning,
            "birds_eye_view": {
                "scope": scope,
                "impact_horizon": impact_horizon,
                "summary": summary,
            },
        }

    def _fetch_headlines(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        status: Dict[str, Any] = {}
        try:
            html_text = self._fetch_html(self.BSE_MOBILE_CORPORATES_URL)
            rows = self._parse_bse_mobile_corporates(html_text)
            status["bse_mobile_corporates"] = {"ok": True, "count": len(rows)}
        except Exception as exc:
            status["bse_mobile_corporates"] = {
                "ok": False,
                "count": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        return rows, status

    def _fetch_kotak_news(self, status: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        try:
            html_text = self._fetch_html(self.KOTAK_NEWS_URL)
            rows = self._parse_kotak_news(html_text)
            status["kotak_news"] = {"ok": True, "count": len(rows), "url": self.KOTAK_NEWS_URL}
        except Exception as exc:
            status["kotak_news"] = {
                "ok": False,
                "count": 0,
                "url": self.KOTAK_NEWS_URL,
                "error": f"{type(exc).__name__}: {exc}",
            }
        return rows

    def _fetch_fii_dii_flow(self, status: Dict[str, Any]) -> Dict[str, Any]:
        try:
            html_text = self._fetch_html(self.KOTAK_FII_DII_URL)
            parsed = self._parse_kotak_fii_dii(html_text)
            status["kotak_fii_dii"] = {
                "ok": bool(parsed),
                "count": 1 if parsed else 0,
                "url": self.KOTAK_FII_DII_URL,
            }
            return parsed
        except Exception as exc:
            status["kotak_fii_dii"] = {
                "ok": False,
                "count": 0,
                "url": self.KOTAK_FII_DII_URL,
                "error": f"{type(exc).__name__}: {exc}",
            }
            return {}

    def _fetch_html(self, url: str) -> str:
        response = self.session.get(
            url,
            timeout=self.timeout_seconds,
            headers={"User-Agent": "Trader-Regime-News/1.0"},
        )
        response.raise_for_status()
        return response.text

    def _parse_kotak_news(self, html_text: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for match in re.finditer(
            r'<a[^>]+href="(?P<href>/news/[^"]+)"[^>]+title="(?P<title>[^"]+)"',
            html_text,
            re.IGNORECASE,
        ):
            title = self._compact_text(html.unescape(match.group("title")))
            href = html.unescape(match.group("href"))
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            context = html_text[match.start() : min(len(html_text), match.end() + 1200)]
            date_match = re.search(r"(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})", self._clean_html_fragment(context))
            category_match = re.search(r">(Stock News|Share Market News)<", context, re.IGNORECASE)
            rows.append(
                {
                    "source": "kotak_news",
                    "section": "market_news",
                    "title": title,
                    "url": urljoin("https://www.kotakneo.com/", href),
                    "published_at_utc": None,
                    "event_date": date_match.group(1) if date_match else None,
                    "company_name": None,
                    "detail_title": title,
                    "detail_subtitle": category_match.group(1) if category_match else None,
                    "detail_text": title,
                    "attachment_url": None,
                    "signal_weight": 0.70,
                }
            )
            if len(rows) >= 20:
                break
        return rows

    def _parse_kotak_fii_dii(self, html_text: str) -> Dict[str, Any]:
        text = self._clean_html_fragment(html_text.replace("<!-- -->", " "))
        date_match = re.search(r"FII\s*&\s*DII\s+Trading\s+Activity\s*:\s*([0-9]{1,2}-[A-Z]{3}-[0-9]{4})", text)
        fii_match = re.search(r"FII\s+₹\s*([+-]?[0-9,]+(?:\.[0-9]+)?)\s*Cr", text)
        dii_match = re.search(r"DII\s+₹\s*([+-]?[0-9,]+(?:\.[0-9]+)?)\s*Cr", text)
        if not (date_match and fii_match and dii_match):
            return {}

        fii_net = self._coerce_float(fii_match.group(1))
        dii_net = self._coerce_float(dii_match.group(1))
        net_combined = None
        if fii_net is not None and dii_net is not None:
            net_combined = round(fii_net + dii_net, 2)

        return {
            "source": "kotak_fii_dii",
            "url": self.KOTAK_FII_DII_URL,
            "as_of_date": date_match.group(1),
            "segment": "cash",
            "fii_net_cash_cr": fii_net,
            "dii_net_cash_cr": dii_net,
            "net_fii_dii_cash_cr": net_combined,
            "summary": (
                f"FII net cash flow {fii_net} Cr; DII net cash flow {dii_net} Cr; "
                f"combined net flow {net_combined} Cr as of {date_match.group(1)}."
            ),
        }

    def _flow_payload_to_headline(self, flow: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "source": "kotak_fii_dii",
            "section": "institutional_flows",
            "title": flow.get("summary") or "FII/DII cash-flow context unavailable.",
            "url": flow.get("url"),
            "published_at_utc": None,
            "event_date": flow.get("as_of_date"),
            "company_name": None,
            "detail_title": "FII/DII cash market flow",
            "detail_subtitle": flow.get("segment"),
            "detail_text": flow.get("summary"),
            "attachment_url": None,
            "signal_weight": 0.85,
            "fii_net_cash_cr": flow.get("fii_net_cash_cr"),
            "dii_net_cash_cr": flow.get("dii_net_cash_cr"),
            "net_fii_dii_cash_cr": flow.get("net_fii_dii_cash_cr"),
        }

    def _parse_bse_mobile_corporates(self, html_text: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        rows.extend(self._parse_bse_announcements(self._extract_div_inner_html(html_text, "divAnnText")))
        rows.extend(self._parse_bse_results(self._extract_div_inner_html(html_text, "divResults")))
        rows.extend(self._parse_bse_corporate_actions(self._extract_div_inner_html(html_text, "divCorpAct")))
        rows.extend(self._parse_bse_offers(self._extract_div_inner_html(html_text, "divIPO")))
        rows.extend(self._parse_bse_listings(self._extract_div_inner_html(html_text, "divListing")))
        return rows

    def _extract_div_inner_html(self, html_text: str, div_id: str) -> str:
        match = re.search(
            rf"<div[^>]+id=['\"]{re.escape(div_id)}['\"][^>]*>(?P<body>.*?)</div>",
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
        return match.group("body") if match else ""

    def _parse_bse_announcements(self, section_html: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for href, label in re.findall(r"<a href='([^']+)'[^>]*>(.*?)</a>", section_html, re.IGNORECASE | re.DOTALL):
            title = self._compact_text(html.unescape(re.sub(r"<[^>]+>", " ", label)))
            if not title:
                continue
            url = urljoin(self.BSE_MOBILE_BASE_URL, href)
            query = parse_qs(urlparse(url).query)
            rows.append(
                {
                    "source": "bse_corporate_announcements",
                    "section": "corporate_announcements",
                    "title": title,
                    "url": url,
                    "published_at_utc": self._extract_bse_datetime_from_title(title),
                    "security_code": (query.get("scrip_CD") or [None])[0],
                    "company_name": title.split(" -", 1)[0].strip() if " -" in title else None,
                    "signal_weight": self.section_weights["corporate_announcements"],
                }
            )
        return rows

    def _parse_bse_results(self, section_html: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for cells in self._extract_table_cells(section_html):
            if len(cells) < 2:
                continue
            security = self._clean_html_fragment(cells[0])
            result_date = self._clean_html_fragment(cells[1])
            if not security:
                continue
            rows.append(
                {
                    "source": "bse_forthcoming_results",
                    "section": "forthcoming_results",
                    "title": f"{security}: scheduled financial results",
                    "url": self.BSE_MOBILE_CORPORATES_URL,
                    "published_at_utc": None,
                    "event_date": result_date or None,
                    "company_name": security,
                    "signal_weight": self.section_weights["forthcoming_results"],
                }
            )
        return rows

    def _parse_bse_corporate_actions(self, section_html: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for cells in self._extract_table_cells(section_html):
            if len(cells) < 3:
                continue
            security = self._clean_html_fragment(cells[0])
            ex_date = self._clean_html_fragment(cells[1])
            purpose = self._clean_html_fragment(cells[2])
            if not security or not purpose:
                continue
            rows.append(
                {
                    "source": "bse_corporate_actions",
                    "section": "corporate_actions",
                    "title": f"{security}: {purpose}",
                    "url": self.BSE_MOBILE_CORPORATES_URL,
                    "published_at_utc": None,
                    "event_date": ex_date or None,
                    "company_name": security,
                    "signal_weight": self.section_weights["corporate_actions"],
                }
            )
        return rows

    def _parse_bse_offers(self, section_html: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for cells in self._extract_table_cells(section_html):
            if len(cells) < 4:
                continue
            security = self._clean_html_fragment(cells[0])
            price_band = self._clean_html_fragment(cells[1])
            issue_period = self._clean_html_fragment(cells[2])
            issue_type = self._clean_html_fragment(cells[3])
            if not security:
                continue
            rows.append(
                {
                    "source": "bse_offers",
                    "section": "offers",
                    "title": (
                        f"{security}: {issue_type or 'offer'} | "
                        f"issue_period={issue_period or 'na'} | price_band={price_band or 'na'}"
                    ),
                    "url": self.BSE_MOBILE_CORPORATES_URL,
                    "published_at_utc": None,
                    "event_date": issue_period or None,
                    "company_name": security,
                    "signal_weight": self.section_weights["offers"],
                }
            )
        return rows

    def _parse_bse_listings(self, section_html: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        text = self._clean_html_fragment(section_html)
        if not text or "no record found" in text.lower():
            return rows
        for chunk in [part.strip() for part in text.split(" | ") if part.strip()]:
            rows.append(
                {
                    "source": "bse_listing_updates",
                    "section": "listing",
                    "title": chunk,
                    "url": self.BSE_MOBILE_CORPORATES_URL,
                    "published_at_utc": None,
                    "signal_weight": self.section_weights["listing"],
                }
            )
        return rows

    def _extract_table_cells(self, section_html: str) -> List[List[str]]:
        rows: List[List[str]] = []
        tr_matches = re.findall(r"<tr>(.*?)</tr>", section_html, re.IGNORECASE | re.DOTALL)
        for tr_html in tr_matches[1:]:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tr_html, re.IGNORECASE | re.DOTALL)
            if cells:
                rows.append(cells)
        return rows

    def _clean_html_fragment(self, value: str) -> str:
        return self._compact_text(html.unescape(re.sub(r"<[^>]+>", " ", value)))

    def _coerce_float(self, value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(",", "").strip())
        except Exception:
            return None

    def _extract_bse_datetime_from_title(self, title: str) -> Optional[str]:
        match = re.search(r"([A-Z][a-z]{2}\s+\d{1,2}\s+\d{4})\s*,\s*(\d{1,2}:\d{2}\s*[AP]M)$", title)
        if not match:
            return None
        try:
            local_dt = datetime.strptime(
                f"{match.group(1)} {match.group(2).replace(' ', '')}",
                "%b %d %Y %I:%M%p",
            )
            local_dt = local_dt.replace(tzinfo=self.market_time.tz)
            return local_dt.astimezone(timezone.utc).isoformat()
        except Exception:
            return None

    def _enrich_bse_announcement_details(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        detail_budget = self.max_detail_fetch
        for row in rows:
            updated = dict(row)
            if detail_budget > 0 and row.get("section") == "corporate_announcements" and row.get("url"):
                detail_budget -= 1
                try:
                    updated.update(self._fetch_bse_announcement_detail(str(row["url"])))
                except Exception as exc:
                    updated["detail_fetch_error"] = f"{type(exc).__name__}: {exc}"
            enriched.append(updated)
        return enriched

    def _fetch_bse_announcement_detail(self, url: str) -> Dict[str, Any]:
        html_text = self._fetch_html(url)
        detail_match = re.search(
            r"<td id=\"tdDet\">(?P<body>.*?)(?:<a href=\"Corporates\.aspx\"|</table>\s*</td>\s*</tr>\s*</table>\s*</div>)",
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
        body = detail_match.group("body") if detail_match else ""
        title_match = re.search(
            r"<td[^>]*class\s*=\s*['\"]ann01['\"][^>]*>(?P<title>.*?)&nbsp;\|&nbsp;<span",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        subtitle_match = re.search(
            r"<td[^>]*class\s*=\s*['\"]ann02['\"][^>]*>(?P<subtitle>.*?)</td>",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        attachment_match = re.search(
            r"href\s*=\s*'(?P<attachment>https://www\.bseindia\.com/[^']+\.pdf)'",
            body,
            re.IGNORECASE,
        )
        return {
            "detail_title": self._clean_html_fragment(title_match.group("title")) if title_match else None,
            "detail_subtitle": self._clean_html_fragment(subtitle_match.group("subtitle")) if subtitle_match else None,
            "detail_text": self._clean_html_fragment(body)[:3000] if body else None,
            "attachment_url": attachment_match.group("attachment").replace("\\", "") if attachment_match else None,
        }

    def _deduplicate_headlines(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: set[str] = set()
        deduped: List[Dict[str, Any]] = []
        for row in rows:
            title_key = re.sub(r"\s+", " ", str(row.get("title", "")).lower()).strip()
            if not title_key or title_key in seen:
                continue
            seen.add(title_key)
            deduped.append(row)
        deduped.sort(key=lambda item: item.get("published_at_utc") or "", reverse=True)
        return deduped

    def _prioritize_headlines(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        def score(item: Dict[str, Any]) -> float:
            blob = f"{item.get('title', '')} {item.get('detail_text', '')}".lower()
            points = float(item.get("signal_weight") or 0.0)
            keywords = {
                "results": 0.30,
                "board": 0.18,
                "dividend": 0.12,
                "buyback": 0.18,
                "merger": 0.28,
                "acquisition": 0.28,
                "management": 0.14,
                "award": 0.18,
                "order": 0.18,
                "fraud": 0.45,
                "default": 0.45,
                "rating": 0.18,
                "fund raise": 0.18,
                "postal ballot": 0.10,
                "clarification": 0.08,
                "regulation 30": 0.08,
            }
            for term, value in keywords.items():
                if term in blob:
                    points += value
            if item.get("attachment_url"):
                points += 0.05
            if item.get("published_at_utc"):
                points += 0.12
            return points

        prioritized = list(rows)
        prioritized.sort(key=score, reverse=True)
        return prioritized

    def _build_section_distribution(self, rows: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for row in rows:
            section = str(row.get("section") or "unknown")
            counts[section] = counts.get(section, 0) + 1
        return counts

    def _compact_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    def _heuristic_summary(self, rows: List[Dict[str, Any]], sentiment: str, severity: float) -> str:
        lead_titles = [self._compact_text(str(item.get("title") or "")) for item in rows[:4]]
        lead_titles = [item for item in lead_titles if item]
        head = " | ".join(lead_titles[:3]) if lead_titles else "No headline previews."
        return f"Sentiment={sentiment}; event_severity={round(severity, 3)}. Top market-context items: {head}"
