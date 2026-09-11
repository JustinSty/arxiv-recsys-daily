"""规则打分。

每条论文返回 score 和 hits，hits 会显示在网页上——调权重时你能一眼看出
某篇论文为什么被选中或漏掉，这比单纯一个分数有用得多。
"""

import re

from filter import searchable_text

_PATTERN_CACHE = {}


def _pattern(term):
    """词边界匹配，避免 'google' 命中 'googlenet' 这类误伤。"""
    if term not in _PATTERN_CACHE:
        escaped = re.escape(term.lower())
        _PATTERN_CACHE[term] = re.compile(rf"(?<!\w){escaped}(?!\w)")
    return _PATTERN_CACHE[term]


def _match_groups(text, groups, label):
    """groups 形如 [{terms: [...], weight: n}]，同组内多次命中只算一次。"""
    score, hits = 0, []
    for group in groups:
        weight = int(group["weight"])
        matched = [t for t in group["terms"] if _pattern(t).search(text)]
        if matched:
            score += weight
            hits.append({"group": label, "terms": matched, "weight": weight})
    return score, hits


def _match_flat(text, terms, weight, label):
    matched = [t for t in terms if _pattern(t).search(text)]
    if not matched:
        return 0, []
    return weight, [{"group": label, "terms": matched, "weight": weight}]


def score_paper(paper, cfg):
    sc = cfg["scoring"]
    text = searchable_text(paper)
    comments = (paper.get("comments", "") + " " + paper.get("journal_ref", "")).lower()

    hits = []

    ind_score, ind_hits = _match_groups(
        text, sc["industrial"]["weight_groups"], "工业信号"
    )
    hits += ind_hits

    # 先把数据集名抹掉再匹配公司，否则 "Amazon Beauty"、"Taobao dataset"
    # 这类公开数据集会被误判成工业信号，进而让条件负向规则失效。
    company_text = text
    for phrase in sc.get("dataset_phrases", []):
        company_text = _pattern(phrase).sub(" ", company_text)

    comp_score, comp_hits = _match_flat(
        company_text, sc["companies"]["terms"], int(sc["companies"]["weight"]), "公司"
    )
    hits += comp_hits
    industrial_total = ind_score + comp_score

    topic_score, topic_hits = _match_groups(text, sc["topics"]["weight_groups"], "主题")
    hits += topic_hits

    venue_score, venue_hits = _match_flat(
        comments, sc["venues"]["terms"], int(sc["venues"]["weight"]), "会议"
    )
    hits += venue_hits

    track_score, track_hits = _match_flat(
        comments,
        sc["industry_tracks"]["terms"],
        int(sc["industry_tracks"]["weight"]),
        "工业 track",
    )
    hits += track_hits

    neg_score, neg_hits = _match_groups(text, sc["negative"]["always"], "负向")
    hits += neg_hits

    if industrial_total == 0:
        cond_score, cond_hits = _match_groups(
            text, sc["negative"]["if_not_industrial"], "负向（无工业信号）"
        )
        neg_score += cond_score
        hits += cond_hits

    total = (
        industrial_total + topic_score + venue_score + track_score + neg_score
    )

    return {
        "score": total,
        "industrial_score": industrial_total,
        "topic_score": topic_score,
        "hits": hits,
    }


def score_all(papers, cfg):
    for p in papers:
        p["scoring"] = score_paper(p, cfg)
    papers.sort(key=lambda p: p["scoring"]["score"], reverse=True)
    return papers
