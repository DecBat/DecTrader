"""
Fetch SEC Form 4 insider transactions directly from SEC EDGAR.

Replaces the Finnhub insider endpoint which hits free-tier rate limits when
scanning 500+ tickers. EDGAR is the primary source — Finnhub just re-packages it.

No API key required. SEC allows ~10 req/sec; we use 150 ms between requests.

First run: downloads a ticker→CIK mapping from the SEC and caches it at
data/sec_cik_mapping.json. Every subsequent run loads from cache. Refresh the
cache occasionally by deleting the file (tickers change ~20-30 times per year).

SEC User-Agent policy: requests must identify the application and provide
contact info. Set SEC_USER_AGENT in .env, or update the default in settings.py.
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import requests

from config.settings import DATA_DIR, SEC_USER_AGENT
from src.utils.logging import get_logger

log = get_logger(__name__)

_CIK_CACHE        = DATA_DIR / "sec_cik_mapping.json"
_CIK_MAP_URL      = "https://www.sec.gov/files/company_tickers.json"
_BASE_SUBMISSIONS = "https://data.sec.gov/submissions"
_BASE_ARCHIVES    = "https://www.sec.gov/Archives/edgar/data"

_HEADERS          = {"User-Agent": SEC_USER_AGENT}
_REQUEST_INTERVAL = 0.15   # 150 ms between requests — stays under SEC's 10 req/sec
_TIMEOUT          = 15     # seconds per request
_SIGNAL_CODES     = {"P", "S"}   # open-market purchase / sale only


# ---------------------------------------------------------------------------
# CIK mapping
# ---------------------------------------------------------------------------

def _get_cik_map() -> dict[str, str]:
    """
    Return {TICKER: '0000000000'} (10-digit zero-padded CIK string).
    Downloads from SEC on first call, then serves from cache.
    """
    if _CIK_CACHE.exists():
        return json.loads(_CIK_CACHE.read_text())

    log.info("Downloading SEC CIK mapping (one-time, cached to %s)...", _CIK_CACHE)
    resp = requests.get(_CIK_MAP_URL, headers=_HEADERS, timeout=30)
    resp.raise_for_status()

    # Response: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "..."}, ...}
    mapping = {
        v["ticker"].upper(): str(v["cik_str"]).zfill(10)
        for v in resp.json().values()
        if "ticker" in v and "cik_str" in v
    }
    _CIK_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CIK_CACHE.write_text(json.dumps(mapping))
    log.info("SEC CIK mapping cached: %d tickers", len(mapping))
    return mapping


# ---------------------------------------------------------------------------
# Form 4 XML parsing
# ---------------------------------------------------------------------------

def _parse_form4(xml_bytes: bytes) -> list[dict]:
    """
    Parse a Form 4 XML document. Returns a list of non-derivative transactions
    using only signal-bearing codes (P = open-market purchase, S = open-market sale).

    Return dict fields match the format previously returned by Finnhub so that
    insider_scorer.py requires no changes:
        name, transactionCode, transactionDate, share, transactionPrice
    """
    transactions = []
    try:
        # Strip XML namespace declarations which break ElementTree XPath queries
        xml_str = xml_bytes.decode("utf-8", errors="replace")
        xml_str = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', "", xml_str)
        root    = ET.fromstring(xml_str)
    except ET.ParseError as exc:
        log.debug("Form 4 XML parse error: %s", exc)
        return transactions

    # Owner name lives outside the transaction elements — pull it once
    owner_el = root.find(".//reportingOwner/reportingOwnerId/rptOwnerName")
    owner    = (owner_el.text or "").strip() if owner_el is not None else "unknown"

    def _val(el: ET.Element, path: str) -> str:
        found = el.find(path)
        return (found.text or "").strip() if found is not None else ""

    for txn in root.findall(".//nonDerivativeTransaction"):
        try:
            code = _val(txn, "transactionCoding/transactionCode")
            if code not in _SIGNAL_CODES:
                continue

            txn_date = _val(txn, "transactionDate/value")
            shares   = float(_val(txn, "transactionAmounts/transactionShares/value") or 0)
            price    = float(_val(txn, "transactionAmounts/transactionPricePerShare/value") or 0)

            if not txn_date or shares == 0:
                continue

            transactions.append({
                "name":             owner,
                "transactionCode":  code,
                "transactionDate":  txn_date,
                "share":            shares,
                "transactionPrice": price,
            })
        except (ValueError, AttributeError):
            continue

    return transactions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_insider_transactions(ticker: str, days: int = 90) -> list[dict]:
    """
    Return a list of open-market insider transactions for *ticker* over the
    last *days* calendar days, sourced from SEC EDGAR Form 4 filings.

    Returns [] if the ticker has no CIK mapping, no recent Form 4 filings,
    or if any network error occurs — callers treat missing data as neutral.
    """
    cik_map = _get_cik_map()
    cik     = cik_map.get(ticker.upper())
    if not cik:
        log.debug("No SEC CIK found for %s — skipping", ticker)
        return []

    cik_int = int(cik)
    cutoff  = date.today() - timedelta(days=days)

    # -- 1. Fetch the submissions index for this company --
    try:
        time.sleep(_REQUEST_INTERVAL)
        resp = requests.get(
            f"{_BASE_SUBMISSIONS}/CIK{cik}.json",
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("EDGAR submissions failed for %s: %s", ticker, exc)
        return []

    recent       = resp.json().get("filings", {}).get("recent", {})
    forms        = recent.get("form",            [])
    dates        = recent.get("filingDate",      [])
    accessions   = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    # -- 2. Download and parse each Form 4 within the date window --
    all_transactions: list[dict] = []

    for form, filing_date, accession, primary_doc in zip(
        forms, dates, accessions, primary_docs
    ):
        if form not in ("4", "4/A"):
            continue
        try:
            if date.fromisoformat(filing_date) < cutoff:
                break   # submissions sorted newest-first — safe to stop
        except ValueError:
            continue

        acc_clean = accession.replace("-", "")
        url = f"{_BASE_ARCHIVES}/{cik_int}/{acc_clean}/{primary_doc}"

        try:
            time.sleep(_REQUEST_INTERVAL)
            xml_resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            xml_resp.raise_for_status()
        except requests.RequestException as exc:
            log.debug("EDGAR Form 4 download failed %s/%s: %s", ticker, accession, exc)
            continue

        txns = _parse_form4(xml_resp.content)
        all_transactions.extend(txns)

    log.debug("EDGAR %s: %d signal transactions in last %dd",
              ticker, len(all_transactions), days)
    return all_transactions
