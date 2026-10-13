"""Render the live documentation graph and command crosswalk."""

from fnmatch import fnmatch

if __package__:
    from .render import (
        code_field,
        esc,
        link,
        links_field,
        page,
        text_field,
        wrap,
    )
else:
    from render import (
        code_field,
        esc,
        link,
        links_field,
        page,
        text_field,
        wrap,
    )

LIVE = "../live/"
LIVE_DOCS = f"{LIVE}docs-graph.html"


def docs_pages(pages, views):
    graph = pages.m.docs_graph
    by_area = {area["id"]: [] for area in graph.get("areas", [])}
    for path in pages.docs:
        area = pages.area_of(path)
        if area:
            by_area[area].append(path)
    inbound = {path: 0 for path in pages.docs}
    for targets in pages.docs.values():
        for target in targets:
            if target in inbound:
                inbound[target] += 1
    index = []
    for area in graph.get("areas", []):
        here = f"{LIVE}docs-graph/{area['id']}.html"
        index.append(f"<h2>{link(LIVE_DOCS, here, area['title'])}</h2>")
        index += text_field("Publication", area["publication"])
        index += text_field("Documents", str(len(by_area[area["id"]])))
        index += links_field(
            "Concepts",
            LIVE_DOCS,
            [pages.concept(c) for c in area.get("concepts", [])],
        )
        body = wrap(
            "<p>Each document with its outbound and inbound links to other "
            "tracked documents. <i>unlinked</i> marks documents no tracked "
            "document links to.</p>"
        ) + ["<ul>"]
        for path in by_area[area["id"]]:
            orphan = "" if inbound[path] else " · <i>unlinked</i>"
            body += wrap(
                f'<li id="{esc(path)}"><a href="{esc("../../../../" + path)}">'
                f"{esc(path)}</a> · out {len(pages.docs[path])} · "
                f"in {inbound[path]}{orphan}</li>"
            )
        views[here] = page(here, area["title"], body + ["</ul>"])
    unassigned = [
        p
        for p in pages.docs
        if not pages.area_of(p)
        and not any(fnmatch(p, row["include"]) for row in graph.get("ungraphed", []))
    ]
    index.append("<h2>Documents in no area</h2>")
    index += code_field("Add an area or ungraphed row in docs-graph.json", unassigned)
    index.append("<h2>Ungraphed areas</h2>")
    for row in graph.get("ungraphed", []):
        count = sum(1 for path in pages.docs if fnmatch(path, row["include"]))
        index += wrap(
            f"<p><code>{esc(row['include'])}</code> · {count} documents · "
            f"{esc(row['reason'])} {link(LIVE_DOCS, 'gaps.html', 'gap', row['gap'])}</p>"
        )
    views[LIVE_DOCS] = page(LIVE_DOCS, "Documentation graph (live)", index)


def commands_page(pages, views):
    used = {k: set() for k in ("commands", "functions", "skills")}
    for node in pages.m.concepts.values():
        for key in used:
            used[key].update(node.get(key, []))
    body = [
        "<p>Live registry totals; mapped ids appear on their concept pages.</p>",
        "<ul>",
    ]
    for key in used:
        body.append(
            f"<li>{esc(key.capitalize())}: {len(pages.live[key])} live, "
            f"{len(used[key])} mapped</li>"
        )
    body.append("</ul>")
    for key in used:
        missing = sorted(set(pages.live[key]) - used[key])
        body.append(
            f'<h2 id="unmapped-{key}">Unmapped {esc(key)} ({len(missing)})</h2>'
        )
        body += code_field("Gap", missing)
    views[f"{LIVE}commands.html"] = page(
        f"{LIVE}commands.html", "Command crosswalk (live)", body
    )
