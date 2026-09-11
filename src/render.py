"""渲染静态产物：当天页面、RSS、历史索引。

页面按「两分钟内决定今天读哪篇」来设计：单栏、细分隔线、标题用衬线体，
命中的关键词直接列出来，方便你调权重时看清楚每篇为什么被选中。
"""

import html
import json
from datetime import datetime, timezone
from email.utils import format_datetime

CSS = """
:root {
  --bg: #f5f6f4;
  --ink: #1a2024;
  --muted: #5e6b70;
  --rule: #dcdfda;
  --accent: #22516b;
  --flag: #8a4b1f;
  --surface: #ffffff;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14181a;
    --ink: #e6e8e4;
    --muted: #939c9f;
    --rule: #2b3134;
    --accent: #7fb3d0;
    --flag: #d39560;
    --surface: #1b2023;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-size: 16px;
  line-height: 1.55;
}
.wrap { max-width: 44rem; margin: 0 auto; padding: 2rem 1.15rem 4rem; }
header { padding-bottom: 1.25rem; border-bottom: 2px solid var(--ink); }
.date { font-size: 2.6rem; line-height: 1; font-weight: 600; letter-spacing: -0.02em; }
.tally { margin-top: 0.5rem; color: var(--muted); font-size: 0.9rem; }
h2 {
  font-size: 0.95rem; font-weight: 600; margin: 2.25rem 0 0.25rem;
  padding-bottom: 0.35rem; border-bottom: 1px solid var(--rule);
}
.paper { padding: 1.4rem 0; border-bottom: 1px solid var(--rule); display: flex; gap: 0.9rem; }
.mark { flex: 0 0 2.1rem; padding-top: 0.35rem; text-align: right; }
.mark .num { font-size: 1.05rem; font-weight: 600; color: var(--accent); }
.mark .sub { display: block; font-size: 0.7rem; color: var(--muted); }
.body { flex: 1 1 auto; min-width: 0; }
.title {
  font-family: Charter, "Iowan Old Style", Georgia, "Songti SC", serif;
  font-size: 1.16rem; line-height: 1.35; margin: 0 0 0.35rem;
}
.title a { color: inherit; text-decoration: none; border-bottom: 1px solid var(--rule); }
.title a:hover, .title a:focus { border-bottom-color: var(--accent); }
.who { color: var(--muted); font-size: 0.85rem; margin-bottom: 0.5rem; }
.zh { margin: 0.5rem 0; }
.why { margin: 0.4rem 0; color: var(--muted); font-size: 0.92rem; }
.flag { color: var(--flag); font-weight: 600; }
.hits { font-size: 0.8rem; color: var(--muted); margin-top: 0.6rem; }
.hits span { display: inline-block; margin-right: 0.7rem; white-space: nowrap; }
.links { font-size: 0.85rem; margin-top: 0.6rem; }
.links a { color: var(--accent); text-decoration: none; margin-right: 0.9rem; }
.links a:hover { text-decoration: underline; }
details { margin-top: 0.6rem; }
summary { cursor: pointer; color: var(--muted); font-size: 0.88rem; }
details .abs { margin-top: 0.5rem; font-size: 0.92rem; color: var(--muted); }
.empty { padding: 2.5rem 0; color: var(--muted); }
footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--rule);
  font-size: 0.85rem; color: var(--muted); }
footer a { color: var(--accent); }
a:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
"""


def esc(s):
    return html.escape(s or "", quote=True)


def _authors(paper, limit=4):
    names = paper.get("authors", [])
    if not names:
        return ""
    shown = "、".join(names[:limit])
    return shown + (f" 等 {len(names)} 人" if len(names) > limit else "")


def _hits_line(paper):
    groups = {}
    for hit in paper["scoring"]["hits"]:
        groups.setdefault(hit["group"], []).extend(hit["terms"])
    if not groups:
        return ""
    parts = [
        f"<span>{esc(g)}：{esc('、'.join(sorted(set(terms))))}</span>"
        for g, terms in groups.items()
    ]
    return f'<div class="hits">{"".join(parts)}</div>'


def _paper_html(paper, rank):
    llm = paper.get("llm", {})
    score = paper["scoring"]["score"]

    zh = f'<p class="zh">{esc(llm["summary_zh"])}</p>' if llm.get("summary_zh") else ""
    why = f'<p class="why">{esc(llm["why_relevant"])}</p>' if llm.get("why_relevant") else ""

    flags = []
    if llm.get("has_online_ab"):
        flags.append("有线上 A/B")
    if llm.get("is_industrial"):
        flags.append("工业界")
    flag_html = f'<p class="why"><span class="flag">{esc(" · ".join(flags))}</span></p>' if flags else ""

    return f"""<article class="paper">
  <div class="mark">
    <span class="num">{rank}</span>
    <span class="sub">{score} 分</span>
  </div>
  <div class="body">
    <h3 class="title"><a href="{esc(paper['abs_url'])}">{esc(paper['title'])}</a></h3>
    <p class="who">{esc(_authors(paper))}</p>
    {zh}{why}{flag_html}
    <details>
      <summary>英文摘要</summary>
      <p class="abs">{esc(paper['abstract'])}</p>
    </details>
    {_hits_line(paper)}
    <p class="links"><a href="{esc(paper['abs_url'])}">arXiv 页面</a><a href="{esc(paper['pdf_url'])}">PDF</a>{f'<span class="who">{esc(paper["comments"])}</span>' if paper.get('comments') else ''}</p>
  </div>
</article>"""


def render_index(papers, cfg, date_str, stats):
    th = cfg["thresholds"]
    must = [p for p in papers if p["scoring"]["score"] >= th["must_read"]]
    maybe = [
        p for p in papers if th["maybe"] <= p["scoring"]["score"] < th["must_read"]
    ]

    blocks = []
    if must:
        blocks.append("<h2>今天读这些</h2>")
        blocks += [_paper_html(p, i) for i, p in enumerate(must, 1)]
    if maybe:
        blocks.append("<h2>可能相关</h2>")
        blocks += [_paper_html(p, i) for i, p in enumerate(maybe, len(must) + 1)]
    if not must and not maybe:
        blocks.append(
            '<p class="empty">今天没有达到阈值的论文。周末和节假日 arXiv 不发布新论文，'
            "工作日出现这种情况可以考虑调低阈值。</p>"
        )

    base = cfg["site"].get("base_url", "").rstrip("/")
    feed_link = f'<a href="{esc(base)}/feed.xml">RSS</a>' if base else '<a href="feed.xml">RSS</a>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(cfg['site']['title'])} · {esc(date_str)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="date">{esc(date_str)}</div>
  <div class="tally">抓取 {stats['total']} 篇，通过硬过滤 {stats['kept']} 篇，达到阈值 {len(must) + len(maybe)} 篇</div>
</header>
{"".join(blocks)}
<footer>
  <p>{feed_link} · <a href="archive.html">历史</a></p>
  <p>数据来自 arXiv，按本地规则打分排序。分数只是排序依据，不代表论文质量。</p>
</footer>
</div>
</body>
</html>"""


def render_feed(papers, cfg, date_str):
    th = cfg["thresholds"]
    items = []
    base = cfg["site"].get("base_url", "").rstrip("/")
    now = format_datetime(datetime.now(timezone.utc))

    for p in papers:
        if p["scoring"]["score"] < th["maybe"]:
            continue
        llm = p.get("llm", {})
        desc_parts = []
        if llm.get("summary_zh"):
            desc_parts.append(llm["summary_zh"])
        if llm.get("why_relevant"):
            desc_parts.append(llm["why_relevant"])
        desc_parts.append(f"规则分 {p['scoring']['score']}")
        desc_parts.append(p["abstract"])
        items.append(
            f"""  <item>
    <title>{esc(p['title'])}</title>
    <link>{esc(p['abs_url'])}</link>
    <guid isPermaLink="true">{esc(p['abs_url'])}</guid>
    <pubDate>{now}</pubDate>
    <description>{esc(" — ".join(desc_parts))}</description>
  </item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{esc(cfg['site']['title'])}</title>
  <link>{esc(base or 'https://arxiv.org/list/cs.IR/new')}</link>
  <description>每日筛选的工业推荐系统论文（{esc(date_str)}）</description>
  <language>zh-cn</language>
  <lastBuildDate>{now}</lastBuildDate>
{chr(10).join(items)}
</channel>
</rss>"""


def render_archive(dates, cfg):
    rows = "".join(
        f'<li><a href="archive/{esc(d["date"])}.html">{esc(d["date"])}</a> '
        f'<span class="who">{d["count"]} 篇</span></li>'
        for d in dates
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>历史 · {esc(cfg['site']['title'])}</title>
<style>{CSS}
ul {{ list-style: none; padding: 0; }}
li {{ padding: 0.7rem 0; border-bottom: 1px solid var(--rule); }}
li a {{ color: var(--ink); text-decoration: none; border-bottom: 1px solid var(--rule); }}
</style>
</head>
<body>
<div class="wrap">
<header><div class="date">历史</div></header>
<ul>{rows}</ul>
<footer><p><a href="index.html">回到今天</a></p></footer>
</div>
</body>
</html>"""


def dump_json(papers, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)
