"""离线冒烟测试：不访问网络，用假的 arXiv 返回跑通整条流水线。

    python tests/smoke_test.py
"""

import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from fetch import parse_atom, utcnow  # noqa: E402
from filter import hard_filter  # noqa: E402
from render import render_archive, render_feed, render_index  # noqa: E402
from score import score_all  # noqa: E402


def fixture():
    now = utcnow()
    recent = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2609.08443v1</id>
    <published>{recent}</published>
    <updated>{recent}</updated>
    <title>End-to-End Ultra-Long Sequence Modeling in Recommendation with Low-Rank Caching</title>
    <summary>We present a system for modeling ultra-long user behavior sequences of up to
      100K events. Our approach uses sequence compression with a low-rank cache to reduce
      serving latency. The system is deployed in production at Douyin and validated through
      online A/B tests serving billions of users.</summary>
    <author><name>Lin Guan</name></author>
    <author><name>Jia-Qi Yang</name></author>
    <author><name>Zhishan Zhao</name></author>
    <author><name>Beichuan Zhang</name></author>
    <author><name>Qiwei Chen</name></author>
    <arxiv:comment>RecSys'26 Industry Track, accepted as a long oral presentation.</arxiv:comment>
    <category term="cs.IR"/>
    <category term="cs.AI"/>
    <arxiv:primary_category term="cs.IR"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2609.06219v1</id>
    <published>{recent}</published>
    <updated>{recent}</updated>
    <title>Closing the Long-Short View Gap in Sequential Recommendation</title>
    <summary>We study sequential recommendation and propose a method that bridges long and
      short term user interest without cached history. Experiments on MovieLens and Amazon
      Beauty show consistent improvements over baselines.</summary>
    <author><name>Lingfeng Shi</name></author>
    <author><name>Chengkai Huang</name></author>
    <arxiv:comment>Accepted at CIKM 2026</arxiv:comment>
    <category term="cs.IR"/>
    <arxiv:primary_category term="cs.IR"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2609.08941v1</id>
    <published>{recent}</published>
    <updated>{recent}</updated>
    <title>A Dataset Recommender System for Recommender-Systems Research</title>
    <summary>We survey available datasets and build a small tool to recommend them to
      researchers. A fairness analysis is included.</summary>
    <author><name>Louis Owie</name></author>
    <arxiv:comment>Bachelor's thesis, University of Siegen, 2026</arxiv:comment>
    <category term="cs.IR"/>
    <arxiv:primary_category term="cs.IR"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2609.00001v1</id>
    <published>{old}</published>
    <updated>{old}</updated>
    <title>An Old Paper Outside The Window</title>
    <summary>This one is about ranking but was submitted a month ago.</summary>
    <author><name>Someone Else</name></author>
    <category term="cs.IR"/>
    <arxiv:primary_category term="cs.IR"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2609.00002v1</id>
    <published>{recent}</published>
    <updated>{recent}</updated>
    <title>Structured Transforms for Low-Overhead Quantization of Language Models</title>
    <summary>A pure NLP paper on quantizing language model weights with structured
      transforms. Nothing here relates to search or personalization.</summary>
    <author><name>Some Author</name></author>
    <category term="cs.LG"/>
    <arxiv:primary_category term="cs.LG"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2609.00003v2</id>
    <published>{recent}</published>
    <updated>{recent}</updated>
    <title>A Revised Version That Should Be Skipped</title>
    <summary>Revision of an earlier ranking paper with online A/B tests at Google.</summary>
    <author><name>Revision Author</name></author>
    <category term="cs.IR"/>
    <arxiv:primary_category term="cs.IR"/>
  </entry>
</feed>"""


def main():
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    papers = parse_atom(fixture().encode("utf-8"))
    assert len(papers) == 6, f"解析出 {len(papers)} 篇，应为 6"
    print(f"解析 {len(papers)} 篇")

    kept, stats = hard_filter(papers, cfg, seen={})
    print(f"硬过滤后 {stats['kept']} 篇 "
          f"(修订版 {stats['revision']}，分类不符 {stats['category']}，过期 {stats['stale']})")
    assert stats["revision"] == 1, "v2 应该被跳过"
    assert stats["category"] == 1, "纯 NLP 的 cs.LG 应该被剔除"
    assert stats["stale"] == 1, "超出时间窗的应该被剔除"
    assert stats["kept"] == 3

    scored = score_all(kept, cfg)
    for p in scored:
        s = p["scoring"]
        print(f"  [{s['score']:>3}] (工业 {s['industrial_score']}, 主题 {s['topic_score']}) "
              f"{p['title'][:60]}")

    top = scored[0]
    assert "Ultra-Long" in top["title"], "工业界长序列论文应该排第一"
    assert top["scoring"]["score"] >= cfg["thresholds"]["must_read"], "它应该进必读"
    assert scored[-1]["scoring"]["score"] < cfg["thresholds"]["maybe"], "本科论文不该上榜"

    # 只在公开数据集上做实验的纯学术论文：不该被当成工业界，应落进「可能相关」
    academic = scored[1]
    assert academic["scoring"]["industrial_score"] == 0, \
        "Amazon Beauty 这类数据集名不该被算作工业信号"
    assert (cfg["thresholds"]["maybe"] <= academic["scoring"]["score"]
            < cfg["thresholds"]["must_read"]), "它应该进折叠区而不是必读"

    # 验证已见过的不会重复出现
    seen = {p["id"]: "2026-09-11" for p in kept}
    _, stats2 = hard_filter(papers, cfg, seen=seen)
    assert stats2["kept"] == 0, "第二次跑应该全部被去重"
    print("去重检查通过")

    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(
        render_index(scored, cfg, "2026-09-11", stats), encoding="utf-8"
    )
    (out / "feed.xml").write_text(
        render_feed(scored, cfg, "2026-09-11"), encoding="utf-8"
    )
    (out / "archive.html").write_text(
        render_archive([{"date": "2026-09-11", "count": 2}], cfg), encoding="utf-8"
    )
    print(f"渲染完成：{(out / 'index.html').stat().st_size} 字节")
    print("\n全部通过")


if __name__ == "__main__":
    main()
