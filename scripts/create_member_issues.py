#!/usr/bin/env python3
"""Create one GitHub issue per team member, assigned to them, listing their tickets.

Reads scripts/tickets.json (mirrors docs/PRD.md Section 21). Each member gets one issue
with every ticket they own as a checklist, grouped by milestone. Safe to re-run: an
issue with the same title is skipped. Uses the GitHub CLI (`gh`), so log in first.

Usage (from the repo root):
    python3 scripts/create_member_issues.py --dry-run
    python3 scripts/create_member_issues.py
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = "SudeeptiSagar/PESU-Agentathon-"
TICKETS = Path(__file__).with_name("tickets.json")
ORDER = ["CP1 Foundation", "CP2 Decision gate", "CP3 Modules", "CP4 First end to end",
         "CP5 Full loop", "Freeze and demo"]
TIMES = {"CP1 Foundation": "19:30", "CP2 Decision gate": "20:30", "CP3 Modules": "23:00",
         "CP4 First end to end": "01:00", "CP5 Full loop": "04:00", "Freeze and demo": "11:00 freeze"}
MEMBERS = [
    ("pruthviprashanth", "Prashanth", "M1", "Core backend and integration (lead)"),
    ("VishalAprameya4", "Vishal", "M2", "UI, frontend and voice"),
    ("SudeeptiSagar", "Sudeepti", "M3", "Browser perception and sites"),
    ("abishekraom", "Abishek", "M4", "Jev, verification and demo"),
]


def gh(args, stdin=None):
    res = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"gh {' '.join(args[:3])} failed:\n{res.stderr or res.stdout}")
    return res.stdout


def body_for(name, mid, role, tickets):
    lines = [f"**{name} ({mid}): {role}**", "",
             "Your tickets for the 24 hours, in checkpoint order. Read `docs/PRD.md` (v3.0) "
             "Sections 10, 12 and 13 first, then paste your block from `docs/TEAM_PROMPTS.md`.", ""]
    for ms in ORDER:
        group = [t for t in tickets if t["milestone"] == ms]
        if not group:
            continue
        lines.append(f"### {ms} ({TIMES[ms]} IST)")
        for t in group:
            dep = "" if t["depends_on"] == "none" else f" (depends on {t['depends_on']})"
            lines.append(f"- [ ] **{t['title']}** {t['priority']}{dep}")
            lines.append(f"  - Done when: {t['acceptance']}")
        lines.append("")
    lines += ["Work one ticket at a time on a branch named `<prefix>/<TICKET-ID>-<short-name>` "
              "and reference this issue in your PRs. Tick items off as they merge."]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    tickets = json.loads(TICKETS.read_text())

    existing = set()
    if not a.dry_run:
        out = gh(["issue", "list", "-R", REPO, "--state", "all", "--limit", "200",
                  "--json", "title", "-q", ".[].title"])
        existing = set(out.splitlines())

    for login, name, mid, role in MEMBERS:
        mine = [t for t in tickets if t["assignee"] == login]
        title = f"[{mid}] {name}: {role} ({len(mine)} tickets)"
        body = body_for(name, mid, role, mine)
        if a.dry_run:
            print(f"--- {title}  -> @{login}\n{body}\n")
            continue
        if title in existing:
            print(f"= {title} (exists)")
            continue
        url = gh(["issue", "create", "-R", REPO, "--title", title, "--assignee", login,
                  "--body-file", "-"], stdin=body).strip()
        print(f"+ {title} -> @{login}  {url}")


if __name__ == "__main__":
    main()
