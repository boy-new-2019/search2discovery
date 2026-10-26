#!/usr/bin/env python3
"""v6.3: Once-per-calendar-year live, official venue authority preflight.

The authority *publication check* is distinct from individual journal/venue
classification. All classifications default to unknown unless actually supported
by a legitimate, separately verified official datum. The 2026 CAS cessation is
not treated as a fictitious 2026 ranking. No paid content is scraped.

Runs local stdlib HTTPS GETs only to explicitly allowlisted official domains.
May be invoked by Codex Desktop's Python tool, not Codex CLI or an agent API.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

SCHEMA = 1
SOURCE_NAMES = ("JCR", "CAS", "CCF")
OFFICIAL_HOSTS = {
    "JCR": ("ir.clarivate.com", "clarivate.com", "journalcitationreports.zendesk.com", "jcr.clarivate.com"),
    "CAS": ("www.las.cas.cn", "las.cas.cn"),
    "CCF": ("www.ccf.org.cn", "ccf.org.cn"),
}
CAS_NOTICE = "https://www.las.cas.cn/news/tzgg/202603/t20260327_8178738.html"
CCF_DIRECTORY = "https://www.ccf.org.cn/Academic_Evaluation/By_category/"
JCR_RELEASE_2026 = "https://ir.clarivate.com/news-events/press-releases/news-details/2026/Clarivate-Releases-Journal-Citation-Reports-2026/default.aspx"
JCR_PRESS_INDEX = "https://ir.clarivate.com/news-events/press-releases/"
JCR_ACCESS_HELP = "https://journalcitationreports.zendesk.com/hc/en-gb/articles/28351249405329-Registration-and-Signing-into-Journal-Citation-Reports"
SOURCE_FACTS_2026 = {
    "JCR": {"known_edition": "2026", "release_date": "2026-06-17", "data_year": "2025", "verified_public_announcement": JCR_RELEASE_2026, "specific_quartiles": "LICENSED_ACCESS_REQUIRED"},
    "CAS": {"last_edition_reference": "2025 (historical; subscription provenance must be independently verified)", "cessation_since": 2026, "official_notice": CAS_NOTICE},
    "CCF": {"known_edition": '7th edition of the CCF Recommended International Academic Conferences and Journals List (official 2026 release, with April erratum)', "release_date": "2026-03-31", "correction_date": "2026-04-09", "official_directory": CCF_DIRECTORY},
}


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def _year(value: int | None = None) -> int:
    y = value if value is not None else now_local().year
    if type(y) is not int or not 2026 <= y <= 2100:
        raise ValueError('Input, evidence or workflow invariant failed at venue_authority._year (check 54); inspect the signed task record and original source.')
    return y


def root(ws: pathlib.Path) -> pathlib.Path:
    return ws.expanduser().resolve() / "output" / "research_cognition" / "venue_authority"


def record_file(ws: pathlib.Path, year: int | None = None) -> pathlib.Path:
    return root(ws) / f"official_authorities_{_year(year)}.json"


def read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp: pathlib.Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".authority_", delete=False) as f:
            tmp = pathlib.Path(f.name)
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp and tmp.exists():
            tmp.unlink()


def source_candidates(source: str, year: int) -> list[str]:
    if source == "JCR":
        # A calendar-year first run may happen before the new annual JCR release.
        # Check that year's candidate, public publisher index, and known official
        # historical publisher announcement (never treat old edition as new).
        expected = f"https://ir.clarivate.com/news-events/press-releases/news-details/{year}/Clarivate-Releases-Journal-Citation-Reports-{year}/default.aspx"
        return list(dict.fromkeys([expected, JCR_PRESS_INDEX, JCR_RELEASE_2026]))
    if source == "CAS":
        return [CAS_NOTICE]  # official service was discontinued in 2026
    if source == "CCF":
        return [CCF_DIRECTORY]
    raise ValueError('Input, evidence or workflow invariant failed at venue_authority.source_candidates (check 97); inspect the signed task record and original source.' + source)


def official_url(source: str, url: str) -> bool:
    p = urllib.parse.urlsplit(url)
    return p.scheme == "https" and not p.username and not p.password and (p.hostname or "").lower() in OFFICIAL_HOSTS[source] and p.port in (None, 443)


class _OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, source: str):
        super().__init__()
        self.source = source

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not official_url(self.source, newurl):
            raise ValueError('Source path, lawful access or network permission check failed at venue_authority.redirect_request (check 112). Do not bypass paywalls or source integrity checks.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(source: str, url: str) -> str:
    """Only fetch public official announcement pages, no login/cookie scraping."""
    if not official_url(source, url):
        raise ValueError('Authentic source, page quotation or evidence integrity check failed at venue_authority.fetch (check 119). Never accept unverified material.' + url)
    opener = urllib.request.build_opener(_OfficialRedirects(source))
    req = urllib.request.Request(url, headers={"User-Agent": "AcademicAuthorityCheck/1.0 (research project; public announcements)", "Accept": "text/html, text/plain"})
    with opener.open(req, timeout=8) as response:
        last = response.geturl()
        if not official_url(source, last):
            raise ValueError('Source path, lawful access or network permission check failed at venue_authority.fetch (check 125). Do not bypass paywalls or source integrity checks.')
        content_type = response.headers.get("Content-Type", "")
        if not any(t in content_type.lower() for t in ("html", "text", "xml")):
            raise ValueError('Authentic source, page quotation or evidence integrity check failed at venue_authority.fetch (check 128). Never accept unverified material.')
        raw = response.read(1100001)
        if len(raw) > 1100000:
            raise ValueError('Authentic source, page quotation or evidence integrity check failed at venue_authority.fetch (check 131). Never accept unverified material.')
        enc = response.headers.get_content_charset() or "utf-8"
        try:
            return raw.decode(enc, errors="replace")
        except LookupError:
            return raw.decode("utf-8", errors="replace")


def cleaned_text(body: str) -> str:
    body = re.sub(r"(?is)<(script|style|noscript)\b[^>]*>.*?</\1>", " ", body)
    body = re.sub(r"<[^>]*>", " ", body)
    return re.sub(r"\s+", " ", html.unescape(body)).strip()


def _find_release(text: str, year: int) -> int | None:
    # A press index can contain many releases. Match the most recent JCR
    # headline, never an unrelated 2027 press item that links to JCR 2026.
    patterns = [r"(?:Clarivate\s+)?(?:Releases|Unveils|Announces|Launches)\s+(?:the\s+)?(?:\d{4}\s+)?Journal\s+Citation\s+Reports\s+(20\d\d)",
                r"(?:Clarivate\s+)?(?:Releases|Unveils|Announces|Launches)\s+(?:the\s+)?(20\d\d)\s+Journal\s+Citation\s+Reports"]
    found = set()
    for p in patterns:
        found.update(int(x) for x in re.findall(p, text, re.IGNORECASE))
    # fallback for JCR newsroom press release wording
    if "Journal Citation Reports" in text and "2026" in text and re.search(r"release(?:d|s)?\s+(?:of\s+)?(?:the\s+)?Journal\s+Citation\s+Reports\s+2026", text, re.I):
        found.add(2026)
    return max((x for x in found if 2025 <= x <= year), default=None)


def assess(source: str, url: str, raw: str, check_year: int) -> dict | None:
    text = cleaned_text(raw)
    if source == "CAS":
        official_org = "\u4e2d\u56fd\u79d1\u5b66\u9662\u6587\u732e\u60c5\u62a5\u4e2d\u5fc3"
        official_stop = "\u4e0d\u518d\u66f4\u65b0\u4e0e\u53d1\u5e03\u671f\u520a\u5206\u533a\u8868"
        if official_org not in text or not re.search(r"\u81ea\s*2026\s*\u5e74\u8d77", text) or official_stop not in text:
            return None
        ed = "DISCONTINUED_SINCE_2026"
        status = "OFFICIAL_CESSATION_VERIFIED"
        excerpt = "The CAS Library and Information Center ceased updating and releasing journal partition tables in 2026."
    elif source == "CCF":
        official_ccf = "\u4e2d\u56fd\u8ba1\u7b97\u673a\u5b66\u4f1a"
        release = "\u6b63\u5f0f\u53d1\u5e03"
        directory = "\u63a8\u8350\u56fd\u9645\u5b66\u672f\u4f1a\u8bae\u548c\u671f\u520a\u76ee\u5f55"
        if not (official_ccf in text and release in text and directory in text):
            return None
        chinese_numerals = "\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341"
        edition_pat = r"\u7b2c(["+chinese_numerals+r"0-9]+)\u7248"
        editions = [int(x) for x in re.findall(edition_pat, text) if x.isdigit()]
        num_map = dict(zip(chinese_numerals, range(1, 11)))
        editions += [num_map[x] for x in re.findall(edition_pat, text) if x in num_map]
        latest = max(editions, default=0)
        if not latest:
            return None
        ed = f"CCF directory edition {latest}"
        status = "OFFICIAL_DIRECTORY_RELEASE_VERIFIED"
        excerpt = "CCF official recommended international conferences and journals directory, formal release."
    elif source == "JCR":
        if "Journal Citation Reports" not in text or "Clarivate" not in text:
            return None
        edition = _find_release(text, check_year)
        if edition is None:
            return None
        ed = str(edition)
        status = "OFFICIAL_EDITION_RELEASE_VERIFIED"
        excerpt = f"Clarivate official announcement: Journal Citation Reports {edition} release."
    else:
        raise ValueError("unknown source")
    return {"status": status, "edition": ed, "verified_url": url,
            "excerpt": excerpt, "page_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "checked_year": check_year, "data_scope":
                ("publication status only; subscription required for per-journal quartile" if source == "JCR"
                 else "published directory/version only; not individual venue classification" if source == "CCF"
                 else "cessation notice only; historical 2025 data require licensed provenance"),
            "edition_is_current_calendar_year": (ed == str(check_year)) if source == "JCR" else None}


def _report(ws: pathlib.Path, record: dict) -> pathlib.Path:
    f = root(ws) / f"official_authorities_{record['calendar_year']}.md"
    lines = [f"# {record['calendar_year']} Official venue authority check", "",
             f"- Checked at: {record['checked_at']}",
             f"- Annual cache status: {record['status']}. Reuse this year's record on later research tasks without repeating network calls.", "",
             "| Authority | Verification result | Published edition or policy | Official source URL | Limits |", "|---|---|---|---|---|"]
    for k in SOURCE_NAMES:
        r = record["sources"][k]
        lines.append("|" + "|".join([k, str(r['status']), str(r.get('edition', 'UNKNOWN')),
                str(r.get('verified_url', 'NOT_VERIFIED')),
                str(r.get('data_scope','Bibliographic metadata, source-page quote matching and agent judgments are distinct epistemic levels. No unperformed simulation, training or experiment provides scientific measurements; verify figures and prior art independently.'))]) + "|")
    lines += ["", "## Important limitations", "",
              "- A release notice is not evidence for every individual journal's JCR quartile. Item-level classification needs legally authorized records.",
              "- CAS journal partition updates stopped from 2026; an authorized 2025 record can be described only as historical 2025 data.",
              "- CCF classifications require matching the precise official directory item, not merely a similar venue name or workshop.",
              "- If sources were blocked or not independently verified, disclose the gap and request a later check. Do not invent a current-year edition.",
              "- JCR specific journal data may require institutional subscription.",
              "", "## Follow-up checks for authentic native research agents", ""]
    for k in SOURCE_NAMES:
        x = record['sources'][k]
        lines.append(f"### {k}")
        lines.extend(f"- {u}" for u in x.get('attempted_urls', []))
        if x.get('errors'):lines.extend(f"- error: {e}" for e in x['errors'])
    f.parent.mkdir(parents=True,exist_ok=True)
    f.write_text("\n".join(lines)+"\n",encoding="utf-8")
    return f


def status(ws: pathlib.Path, *, year: int | None = None) -> dict:
    y = _year(year)
    path = record_file(ws, y)
    if not path.is_file():
        return {"status": "ANNUAL_OFFICIAL_CHECK_REQUIRED", "calendar_year": y,
                "first_run_this_year": True, "should_search": True,
                "next": 'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    rec = read_json(path)
    if rec.get('schema_version')!=SCHEMA or rec.get('calendar_year')!=y or set(rec.get('sources',{}))!=set(SOURCE_NAMES):
        return {"status": "ANNUAL_CACHE_INVALID_NEEDS_RECHECK", "calendar_year": y,
                "should_search": True, "next": 'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    return {"status": rec['status'], "calendar_year": y, "first_run_this_year": False,
            "should_search": False, "checked_at": rec['checked_at'],
            "official_coverage": {k:r.get('status') for k,r in rec['sources'].items()},
            "editions": {k:r.get('edition', 'UNKNOWN') for k,r in rec['sources'].items()},
            "publication_check_complete": all(r.get('verified_url') for r in rec['sources'].values()),
            "specific_journal_rankings_verified": False,
            "cache_path": str(path), "report": str(root(ws)/f"official_authorities_{y}.md"),
            "next": 'Inspect the signed checkpoint, verify the original full-text evidence and reviewer receipts, then continue only the stage justified by a substantive evidence gap and available quota.'}


def check(ws: pathlib.Path, *, year: int | None = None, online: bool = False,
          force: bool = False, fetcher: Callable[[str,str],str] | None = None) -> dict:
    y = _year(year)
    ws = ws.expanduser().resolve()
    old = status(ws,year=y)
    if not old['should_search'] and not force:
        return {**old, "cache_reused": True, "network_requests": 0}
    if not online:
        return {**old, "status": "ANNUAL_OFFICIAL_CHECK_REQUIRES_NETWORK", "cache_reused": False,
                "network_requests": 0}
    f = fetcher or fetch
    started = now_local().isoformat(timespec='seconds')
    attempts = 0
    rec = {"schema_version": SCHEMA, "calendar_year": y, "checked_at": started,
           "verified_publication_is_not_verified_rank": True, "sources": {},
           "historical_context_as_of_2026": SOURCE_FACTS_2026,
           "read_only_original_research": True}
    for src in SOURCE_NAMES:
        errors=[]; result=None; attempted=[]
        for url in source_candidates(src,y):
            if not official_url(src,url):raise ValueError("unsafe official URL template")
            attempted.append(url)
            try:
                attempts+=1
                body=f(src,url)
                candidate=assess(src,url,body,y)
                if candidate is None:
                    errors.append("OFFICIAL_PAGE_NOT_SEMANTICALLY_VERIFIABLE:"+url)
                    continue
                if result is None or (src=="JCR" and int(candidate['edition'])>int(result['edition'])):
                    result=candidate
                # For CCF and CAS, the authoritative current directory/notice is unique.
                if src in ('CAS','CCF') or (src=='JCR' and candidate['edition']==str(y)):
                    break
            except (ValueError, OSError, TimeoutError, UnicodeError, urllib.error.URLError, urllib.error.HTTPError) as exc:
                errors.append(type(exc).__name__+":"+str(exc)[:190])
                continue
        if result is None:
            result={"status": "OFFICIAL_ACCESS_OR_CONTENT_NOT_VERIFIED", "edition": "UNKNOWN",
                    "verified_url": "", "data_scope": 'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
        result['attempted_urls']=attempted
        result['errors']=errors
        if src=='CAS':result['cessation_policy_effective_from']=2026 if result.get('verified_url') else None
        if src=='JCR':result['specific_journal_quartiles']='NOT_VERIFIED_REQUIRE_LICENSED_JCR_ACCESS'
        rec['sources'][src]=result
    rec['status']='ANNUAL_OFFICIAL_CHECK_COMPLETED' if all(r['verified_url'] for r in rec['sources'].values()) else 'ANNUAL_OFFICIAL_CHECK_PARTIAL'
    rec['requests_attempted']=attempts
    previous=record_file(ws,y)
    if previous.is_file():
        # An explicit mid-year refresh does not destroy the original record.
        old=previous.read_bytes()
        key=hashlib.sha256(old).hexdigest()
        archived=root(ws)/'revision_history'/f'{y}_{key}.json'
        archived.parent.mkdir(parents=True,exist_ok=True)
        if not archived.exists():archived.write_bytes(old)
    atomic_json(previous,rec)
    queue={"schema_version": SCHEMA, "calendar_year": y,
           "task": "Use actual Codex Desktop web search to verify official notices when machine HTTPS retrieval was blocked; do not claim individual journal ranks without official licensed evidence.",
           "missing_official_sources": [], "jcr_specific_quartiles": "REQUIRES_LEGITIMATE_INSTITUTIONAL_SUBSCRIPTION"}
    lookup={"JCR":f'site:ir.clarivate.com Journal Citation Reports {y} official release',
            "CCF":'This section indexes existing source-verified reviewer observations. It does not certify scientific validity, novelty or new experimental outcomes.',
            "CAS":'Research evidence and workflow notes (venue_authority.check). Use original source evidence; keep frozen constraints and independent quality gates.'}
    for src in SOURCE_NAMES:
        z=rec['sources'][src]
        if not z.get('verified_url') or (src=='JCR' and z.get('edition_is_current_calendar_year') is False):
            queue['missing_official_sources'].append({"source":src,"official_domains":OFFICIAL_HOSTS[src],
                 "official_source_query":lookup[src],"attempted_urls":z.get('attempted_urls',[]),
                 "known_prior_release_not_equal_to_verified_current_release":src=='JCR' and bool(z.get('verified_url'))})
    atomic_json(root(ws)/f'official_recheck_tasks_{y}.json',queue)
    report=_report(ws,rec)
    return {**status(ws,year=y), "network_requests": attempts, "cache_reused": False, "report":str(report),
            "native_official_review_tasks":str(root(ws)/f'official_recheck_tasks_{y}.json')}


def main(argv=None):
    p=argparse.ArgumentParser(description='This section indexes existing source-verified reviewer observations. It does not certify scientific validity, novelty or new experimental outcomes.')
    p.add_argument('operation',choices=('status','check','refresh','report'))
    p.add_argument('--workspace',type=pathlib.Path,required=True)
    p.add_argument('--online',action='store_true',help='Research evidence and workflow notes (venue_authority.main). Use original source evidence; keep frozen constraints and independent quality gates.')
    p.add_argument('--year',type=int,help='Research evidence and workflow notes (venue_authority.main). Use original source evidence; keep frozen constraints and independent quality gates.')
    x=p.parse_args(argv)
    try:
        if x.operation=='status':result=status(x.workspace,year=x.year)
        elif x.operation=='report':result=status(x.workspace,year=x.year)
        else:result=check(x.workspace,year=x.year,online=x.online,force=x.operation=='refresh')
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,RuntimeError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc)},ensure_ascii=False))
        return 2

if __name__=='__main__':raise SystemExit(main())
