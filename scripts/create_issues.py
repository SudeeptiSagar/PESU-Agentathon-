#!/usr/bin/env python3
"""Create the PRD ticket backlog as GitHub issues.

Reads scripts/tickets.json (mirrors docs/PRD.md Section 21) and creates, through the
GitHub CLI (`gh`), the labels, milestones and issues, with assignees. Safe to re-run:
existing labels, milestones and issues (matched by title) are skipped.

Usage (from the repo root, logged in with `gh auth login` as a collaborator):
    python3 scripts/create_issues.py --dry-run     # show what would be created
    python3 scripts/create_issues.py               # create everything
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = "SudeeptiSagar/PESU-Agentathon-"
TICKETS = Path(__file__).with_name("tickets.json")

LABELS = {
    "role:core": ("1d76db", "M1 core backend and integration (Prashanth)"),
    "role:ui": ("5319e7", "M2 UI, frontend and voice (Vishal)"),
    "role:browser": ("0e8a16", "M3 browser perception and sites (Sudeepti)"),
    "role:jev-demo": ("d93f0b", "M4 Jev, verification and demo (Abishek)"),
    "P0": ("b60205", "Must ship"),
    "P1": ("fbca04", "Should ship"),
    "P2": ("c5def5", "Nice to have"),
    "blocked": ("000000", "Waiting on another ticket or decision"),
    "bug": ("ee0701", "Something is broken"),
    "decision": ("006b75", "Produces a decision the team must act on"),
}

MILESTONES = [
    ("CP1 Foundation", "19:30 IST: skeleton on main, environments, Handy installed, Jev access known"),
    ("CP2 Decision gate", "20:30 IST: Handy pass/fail, LLM reliability, gate backend chosen"),
    ("CP3 Modules", "23:00 IST: every P0 module passes its acceptance check and is merged"),
    ("CP4 First end to end", "01:00 IST: typed requests complete demo tasks A and B"),
    ("CP5 Full loop", "04:00 IST: voice end to end, gate, irreversible hold and human check wired, trap caught"),
    ("Freeze and demo", "11:00 IST freeze, rehearsals, backup video, submission"),
]


def gh(args, payload=None, check=True):
    """Run `gh api` and return parsed JSON (or None)."""
    cmd = ["gh", "api", *args]
    if payload is not None:
        cmd += ["--input", "-"]
    res = subprocess.run(cmd, input=json.dumps(payload) if payload is not None else None,
                         capture_output=True, text=True)
    if res.returncode != 0:
        if check:
            sys.exit(f"gh api {' '.join(args)} failed:\n{res.stderr or res.stdout}")
        return None
    return json.loads(res.stdout) if res.stdout.strip() else None


def paged(path):
    items, page = [], 1
    while True:
        batch = gh([f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}"])
        if not batch:
            return items
        items += batch
        page += 1


def body_for(t, numbers=None):
    deps = t["depends_on"]
    if numbers:
        deps = re.sub(r"(CORE|UI|BRW|JEV)-\d+",
                      lambda m: f"{m.group(0)} (#{numbers[m.group(0)]})" if m.group(0) in numbers else m.group(0),
                      deps)
    items = [c.strip() for c in t["acceptance"].split(";") if c.strip()]
    checks = "\n".join(f"- [ ] {c[0].upper() + c[1:]}" for c in items)
    return (
        f"**Ticket:** {t['id']}  \n"
        f"**Owner:** {t['owner']}  \n"
        f"**Priority:** {t['priority']}  \n"
        f"**Milestone:** {t['milestone']}  \n"
        f"**Depends on:** {deps}\n\n"
        f"### Acceptance criteria\n{checks}\n\n"
        f"### References\n"
        f"- `docs/PRD.md` Section 12 (interface contract) and Section 10 (hard safety rules)\n"
        f"- `docs/PRD.md` Section 21 (backlog)\n\n"
        f"Branch: `{branch_prefix(t['id'])}/{t['id']}-<short-name>`. "
        f"Close with `Closes #<this issue>` in the PR."
    )


def branch_prefix(tid):
    return {"CORE": "core", "UI": "ui", "BRW": "browser", "JEV": "jev"}[tid.split("-")[0]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-assign", action="store_true", help="create issues without assignees")
    a = ap.parse_args()
    tickets = json.loads(TICKETS.read_text())

    if a.dry_run:
        for t in tickets:
            print(f"{t['title']}  -> @{t['assignee']}  [{', '.join(t['labels'])}]  ({t['milestone']})")
        print(f"\n{len(tickets)} issues, {len(LABELS)} labels, {len(MILESTONES)} milestones would be ensured.")
        return

    # Labels
    existing = {l["name"] for l in paged(f"repos/{REPO}/labels")}
    for name, (color, desc) in LABELS.items():
        if name not in existing:
            gh([f"repos/{REPO}/labels", "-X", "POST"], {"name": name, "color": color, "description": desc})
            print(f"label   + {name}")

    # Milestones
    ms = {m["title"]: m["number"] for m in paged(f"repos/{REPO}/milestones?state=all")}
    for title, desc in MILESTONES:
        if title not in ms:
            m = gh([f"repos/{REPO}/milestones", "-X", "POST"], {"title": title, "description": desc})
            ms[title] = m["number"]
            print(f"milestone + {title}")

    # Issues
    by_title = {i["title"]: i["number"] for i in paged(f"repos/{REPO}/issues?state=all")
                if "pull_request" not in i}
    numbers = {}
    for t in tickets:
        if t["title"] in by_title:
            numbers[t["id"]] = by_title[t["title"]]
            print(f"issue   = {t['title']} (#{numbers[t['id']]}, exists)")
            continue
        payload = {"title": t["title"], "body": body_for(t), "labels": t["labels"],
                   "milestone": ms[t["milestone"]]}
        if not a.no_assign:
            payload["assignees"] = [t["assignee"]]
        issue = gh([f"repos/{REPO}/issues", "-X", "POST"], payload)
        numbers[t["id"]] = issue["number"]
        print(f"issue   + {t['title']} (#{issue['number']}) -> @{t['assignee']}")

    # Second pass: link dependencies to issue numbers
    for t in tickets:
        if re.search(r"(CORE|UI|BRW|JEV)-\d+", t["depends_on"]):
            gh([f"repos/{REPO}/issues/{numbers[t['id']]}", "-X", "PATCH"], {"body": body_for(t, numbers)})
    print(f"\nDone: {len(numbers)} issues. https://github.com/{REPO}/issues")


if __name__ == "__main__":
    main()
