from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(r"D:\clawlearn\openclawskills_repo\skills")
SKILLS = [
    "BLY-info-search-planner",
    "BLY-info-search-executor",
    "BLY-info-source-verifier",
    "BLY-info-news-verifier",
    "BLY-info-evidence-pack",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise ValueError("missing YAML frontmatter")
    data = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def main() -> int:
    results = []
    for skill_name in SKILLS:
        skill_dir = ROOT / skill_name
        skill_md = skill_dir / "SKILL.md"
        evals_json = skill_dir / "evals" / "evals.json"
        templates = list((skill_dir / "templates").glob("*.md"))

        skill_text = read_text(skill_md)
        fm = extract_frontmatter(skill_text)
        evals = json.loads(read_text(evals_json))

        checks = {
            "frontmatter_name_matches": fm.get("name") == skill_name,
            "description_mentions_use": "Use this skill" in skill_text,
            "has_output_or_workflow_section": any(
                marker in skill_text
                for marker in ["## Output format", "## Planner workflow", "## Verification workflow", "## Evidence-pack workflow"]
            ),
            "has_template": bool(templates),
            "has_minimum_evals": len(evals.get("evals", [])) >= 3,
        }

        results.append(
            {
                "skill": skill_name,
                "checks": checks,
                "passed": all(checks.values()),
            }
        )

    report = {
        "suite": "BLY info skills",
        "results": results,
        "all_passed": all(item["passed"] for item in results),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
