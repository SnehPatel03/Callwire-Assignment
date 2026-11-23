"""Summary dict -> human-readable Markdown."""

_BADGE = {"full": "✅", "number_only": "🟡", True: "✅"}


def to_markdown(s: dict) -> str:
    lines = [
        f"# {s['company']} — {s.get('quarter') or 'Concall'} ({s['call_date']})",
        f"*Source: {s['source']} · {s['source_url']} · filed {s.get('filing_date')}*",
        "",
        "## TL;DR",
    ]
    lines += [f"- {x}" for x in s["tldr"]]

    for title, key in (("Management commentary", "management_commentary"),
                       ("Guidance / outlook", "guidance"),
                       ("Risks / concerns", "risks")):
        lines += ["", f"## {title}"] + [f"- {x}" for x in s[key]]

    lines += ["", "## Segment performance"]
    lines += [f"- **{x['segment']}**: {x['notes']}" for x in s["segment_performance"]]

    lines += ["", "## Key numbers",
              "| Metric | Entity | Period | Value | Context | Verified |",
              "|---|---|---|---|---|---|"]
    lines += [
        f"| {x['metric']} | {x.get('entity', '')} | {x.get('period', '')} | {x['value']} | "
        f"{x.get('context', '')} | {_BADGE.get(x.get('verified'), '⚠️')} |"
        for x in s["key_metrics"]
    ]

    lines += ["", "## Notable Q&A"]
    lines += [
        f"**Q ({x.get('asked_by', 'not stated')}):** {x['question']}\n\n"
        f"**A (Answered by {x.get('answered_by') or 'Management'}):** {x['answer']}\n"
        for x in s["notable_qa"]
    ]

    tone = s.get("tone") or {}
    lines += ["", f"## Management tone: {tone.get('label', '')}", tone.get("reason", "")]
    return "\n".join(lines)
