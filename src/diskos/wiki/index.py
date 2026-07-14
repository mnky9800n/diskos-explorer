"""Maintain the wiki's index.md (content catalog) and log.md (chronological).

index.md is upserted per entry (keyed by link target, so re-ingesting refreshes
the line rather than duplicating). log.md is append-only with the greppable
``## [date] op | title`` prefix.
"""

from __future__ import annotations

from pathlib import Path

INDEX = "index.md"
LOG = "log.md"


def append_log(wiki_dir: str | Path, on_date: str, op: str, title: str) -> None:
    """Append one chronological entry to log.md."""
    path = Path(wiki_dir) / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"## [{on_date}] {op} | {title}\n")


def upsert_index_entry(
    wiki_dir: str | Path,
    section_title: str,
    relpath: str,
    title: str,
    summary: str,
) -> None:
    """Insert or refresh a catalog line under ``section_title``.

    The line is ``- [title](relpath): summary``. Existing lines for the same
    relpath are replaced (no duplicates). No em dashes in generated content.
    """
    path = Path(wiki_dir) / INDEX
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Wiki Index\n\n## {section_title}\n", encoding="utf-8")

    lines = path.read_text(encoding="utf-8").splitlines()
    marker = f"]({relpath})"
    new_line = f"- [{title}]({relpath}): {summary}"

    section = next(
        (i for i, l in enumerate(lines)
         if l.startswith("## ") and section_title.lower() in l.lower()),
        None,
    )
    if section is None:
        lines += ["", f"## {section_title}", new_line]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    end = next((k for k in range(section + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
    for k in range(section + 1, end):
        if marker in lines[k]:
            lines[k] = new_line
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return

    insert_at = end
    while insert_at - 1 > section and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    lines.insert(insert_at, new_line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
