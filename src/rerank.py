"""用 Claude 对规则分较高的论文做二次筛选，并写一句话中文摘要。

没有 ANTHROPIC_API_KEY 时整个步骤跳过，流水线照常出结果。
"""

import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"

PROMPT = """你在帮一位工业界推荐系统工程师做每日论文筛选。

他关注的方向：
{interests}

下面是一篇 arXiv 论文：

标题：{title}
作者：{authors}
备注：{comments}
摘要：{abstract}

请判断这篇论文对他的价值，只返回一个 JSON 对象，不要有任何前后文字或 markdown 代码块：
{{"relevance": 0-10 的整数, "is_industrial": true 或 false, "has_online_ab": true 或 false, "summary_zh": "一句话中文摘要，说清楚解决什么问题、用什么方法", "why_relevant": "一句话说明和他关注方向的关系；若不相关就说明为什么"}}

relevance 评分标准：8 分以上表示他今天应该放下手头的事去读；5-7 分值得扫一眼摘要；4 分以下不值得看。
"""


def _call(model, prompt, api_key, timeout=60):
    payload = {
        "model": model,
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read())

    text = "".join(
        block.get("text", "") for block in body.get("content", []) if block.get("type") == "text"
    )
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)


def rerank(papers, cfg):
    rc = cfg.get("rerank", {})
    if not rc.get("enabled", False):
        return papers, "rerank 未启用"

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return papers, "未配置 ANTHROPIC_API_KEY，跳过 LLM 筛选"

    candidates = [
        p
        for p in papers
        if p["scoring"]["score"] >= int(rc.get("min_rule_score", 5))
    ][: int(rc.get("max_papers", 15))]

    ok, failed = 0, 0
    for paper in candidates:
        prompt = PROMPT.format(
            interests=rc.get("interests", "").strip(),
            title=paper["title"],
            authors=", ".join(paper["authors"][:6]),
            comments=paper.get("comments", "") or "（无）",
            abstract=paper["abstract"],
        )
        try:
            result = _call(rc.get("model", "claude-sonnet-5"), prompt, api_key)
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError):
            # 单篇失败不影响整体，规则分仍然有效
            failed += 1
            continue

        paper["llm"] = result
        ok += 1

    # 综合排序：规则分归一化后与 LLM 相关性加权
    max_rule = max((p["scoring"]["score"] for p in papers), default=1) or 1
    for p in papers:
        rule_norm = p["scoring"]["score"] / max_rule * 10
        llm_rel = p.get("llm", {}).get("relevance")
        p["final_score"] = (
            0.4 * rule_norm + 0.6 * llm_rel if llm_rel is not None else rule_norm
        )
    papers.sort(key=lambda p: p["final_score"], reverse=True)

    return papers, f"LLM 筛选完成：成功 {ok} 篇，失败 {failed} 篇"
