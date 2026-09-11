"""硬过滤：在打分之前砍掉明显不需要的条目。

顺序：已见过 -> 修订版 -> 分类 -> 时间窗口。
"""

from datetime import timedelta

from fetch import parse_date, utcnow


def searchable_text(paper):
    """打分和过滤统一看这一坨文本。"""
    parts = [
        paper.get("title", ""),
        paper.get("abstract", ""),
        paper.get("comments", ""),
        paper.get("journal_ref", ""),
        " ".join(paper.get("authors", [])),
    ]
    return " ".join(parts).lower()


def category_ok(paper, fc):
    cats = set(paper.get("categories", []))
    if cats & set(fc["required_categories"]):
        return True
    if cats & set(fc["aux_categories"]):
        text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
        return any(kw.lower() in text for kw in fc["aux_keywords"])
    return False


def hard_filter(papers, cfg, seen):
    fc = cfg["fetch"]
    cutoff = utcnow() - timedelta(days=int(fc["window_days"]))

    kept, stats = [], {
        "total": len(papers),
        "seen": 0,
        "revision": 0,
        "category": 0,
        "stale": 0,
    }

    for p in papers:
        if p["id"] in seen:
            stats["seen"] += 1
            continue
        if fc.get("skip_revisions", True) and p.get("version", 1) > 1:
            stats["revision"] += 1
            continue
        if not category_ok(p, fc):
            stats["category"] += 1
            continue

        published = parse_date(p.get("published"))
        if published and published < cutoff:
            stats["stale"] += 1
            continue

        kept.append(p)

    stats["kept"] = len(kept)
    return kept, stats
