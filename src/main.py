"""每日入口。

    python src/main.py                 # 正常跑
    python src/main.py --dry-run       # 抓取并打分，但不写任何文件
    python src/main.py --rescore       # 不抓 arXiv，用存档重跑打分（调权重时用这个）
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))

import yaml  # noqa: E402

from fetch import fetch  # noqa: E402
from filter import hard_filter  # noqa: E402
from render import (  # noqa: E402
    dump_json,
    render_archive,
    render_feed,
    render_index,
)
from rerank import rerank  # noqa: E402
from score import score_all  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ARCHIVE = DATA / "archive"
DOCS = ROOT / "docs"


def load_config():
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen():
    path = DATA / "seen.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(seen, cfg):
    # 只保留最近一段时间，避免文件无限膨胀
    keep = int(cfg["site"].get("keep_archive_days", 180))
    if len(seen) > keep * 200:
        items = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)
        seen = dict(items[: keep * 200])
    DATA.mkdir(parents=True, exist_ok=True)
    with open(DATA / "seen.json", "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=0, sort_keys=True)


def today_str(cfg):
    tz = ZoneInfo(cfg["site"].get("timezone", "UTC"))
    return datetime.now(tz).strftime("%Y-%m-%d")


def build_archive_index(cfg):
    entries = []
    for path in sorted(ARCHIVE.glob("*.json"), reverse=True):
        try:
            with open(path, encoding="utf-8") as f:
                papers = json.load(f)
        except json.JSONDecodeError:
            continue
        shown = [
            p for p in papers
            if p.get("scoring", {}).get("score", 0) >= cfg["thresholds"]["maybe"]
        ]
        entries.append({"date": path.stem, "count": len(shown)})
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="不写文件")
    ap.add_argument("--rescore", metavar="DATE", help="用存档重跑打分，不访问 arXiv")
    args = ap.parse_args()

    cfg = load_config()
    date_str = args.rescore or today_str(cfg)

    if args.rescore:
        with open(ARCHIVE / f"{args.rescore}.json", encoding="utf-8") as f:
            papers = json.load(f)
        stats = {"total": len(papers), "kept": len(papers)}
        print(f"从存档重跑 {args.rescore}，共 {len(papers)} 篇")
    else:
        seen = load_seen()
        raw = fetch(cfg)
        print(f"arXiv 返回 {len(raw)} 篇")
        papers, stats = hard_filter(raw, cfg, seen)
        print(
            f"硬过滤：已见 {stats['seen']}，修订版 {stats['revision']}，"
            f"分类不符 {stats['category']}，超出时间窗 {stats['stale']}，保留 {stats['kept']}"
        )

    papers = score_all(papers, cfg)
    papers, note = rerank(papers, cfg)
    print(note)

    th = cfg["thresholds"]
    shown = [p for p in papers if p["scoring"]["score"] >= th["maybe"]]
    print(f"达到阈值 {len(shown)} 篇，其中必读 "
          f"{len([p for p in papers if p['scoring']['score'] >= th['must_read']])} 篇")

    for p in shown[:5]:
        print(f"  [{p['scoring']['score']:>3}] {p['title'][:70]}")

    if args.dry_run:
        print("dry-run，未写入任何文件")
        return

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "archive").mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)

    index_html = render_index(papers, cfg, date_str, stats)
    (DOCS / "index.html").write_text(index_html, encoding="utf-8")
    (DOCS / "archive" / f"{date_str}.html").write_text(index_html, encoding="utf-8")
    (DOCS / "feed.xml").write_text(render_feed(papers, cfg, date_str), encoding="utf-8")

    dump_json(papers, ARCHIVE / f"{date_str}.json")
    (DOCS / "archive.html").write_text(
        render_archive(build_archive_index(cfg), cfg), encoding="utf-8"
    )
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    if not args.rescore:
        seen = load_seen()
        for p in papers:
            seen.setdefault(p["id"], date_str)
        save_seen(seen, cfg)

    print(f"已写入 docs/index.html 和 data/archive/{date_str}.json")


if __name__ == "__main__":
    main()
