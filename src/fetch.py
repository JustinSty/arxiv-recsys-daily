"""从 arXiv 官方 API 抓取最新论文。

只用标准库，不需要 requests/feedparser，减少 CI 里的依赖问题。
"""

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

API_URL = "http://export.arxiv.org/api/query"

NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# arXiv 明确要求带一个能联系到你的 UA
USER_AGENT = "arxiv-recsys-daily/1.0 (personal paper digest; contact via GitHub issues)"

_ID_RE = re.compile(r"abs/(?P<base>.+?)(?:v(?P<version>\d+))?$")


def _text(node, path, default=""):
    found = node.find(path, NS)
    if found is None or found.text is None:
        return default
    return re.sub(r"\s+", " ", found.text).strip()


def _parse_entry(entry):
    raw_id = _text(entry, "a:id")
    m = _ID_RE.search(raw_id)
    if not m:
        return None
    base_id = m.group("base")
    version = int(m.group("version") or 1)

    authors = [
        re.sub(r"\s+", " ", n.text).strip()
        for n in entry.findall("a:author/a:name", NS)
        if n.text
    ]
    categories = [
        c.get("term") for c in entry.findall("a:category", NS) if c.get("term")
    ]

    return {
        "id": base_id,
        "version": version,
        "title": _text(entry, "a:title"),
        "abstract": _text(entry, "a:summary"),
        "authors": authors,
        "comments": _text(entry, "arxiv:comment"),
        "journal_ref": _text(entry, "arxiv:journal_ref"),
        "categories": categories,
        "primary_category": (
            entry.find("arxiv:primary_category", NS).get("term")
            if entry.find("arxiv:primary_category", NS) is not None
            else (categories[0] if categories else "")
        ),
        "published": _text(entry, "a:published"),
        "updated": _text(entry, "a:updated"),
        "abs_url": f"https://arxiv.org/abs/{base_id}",
        "pdf_url": f"https://arxiv.org/pdf/{base_id}",
    }


def parse_atom(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = []
    for entry in root.findall("a:entry", NS):
        parsed = _parse_entry(entry)
        if parsed:
            out.append(parsed)
    return out


def _build_search_query(required, aux):
    cats = list(required) + list(aux)
    return " OR ".join(f"cat:{c}" for c in cats)


def fetch(cfg, opener=None):
    """按配置抓取，返回去重后的论文列表（最新的在前）。"""
    fc = cfg["fetch"]
    query = _build_search_query(fc["required_categories"], fc["aux_categories"])

    papers = {}
    page_size = int(fc["page_size"])
    max_results = int(fc["max_results"])

    for start in range(0, max_results, page_size):
        params = {
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "start": start,
            "max_results": min(page_size, max_results - start),
        }
        url = f"{API_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

        fetcher = opener or urllib.request.urlopen
        with fetcher(req, timeout=90) as resp:
            body = resp.read()

        batch = parse_atom(body)
        if not batch:
            break
        for p in batch:
            papers.setdefault(p["id"], p)
        if len(batch) < params["max_results"]:
            break

        # arXiv 要求请求之间留间隔，别改小
        time.sleep(float(fc["sleep_seconds"]))

    return list(papers.values())


def parse_date(value):
    """把 arXiv 的 ISO 时间串转成 aware datetime。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def utcnow():
    return datetime.now(timezone.utc)
