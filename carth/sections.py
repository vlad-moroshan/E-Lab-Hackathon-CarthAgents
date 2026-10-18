"""Source-line ownership shared by runtime resolution and evaluation."""
from __future__ import annotations


def section_views(spec, views, diagnostics=None):
    """Select explicit source lines/ranges inside a sheet or listed pages. Reject ambiguous ownership.

    Legacy sections without boundaries are supported only where their container has a unique owner.
    Parallel tables may share lines if they explicitly select them and use disjoint source columns.
    """
    diagnostics = diagnostics if diagnostics is not None else []
    selected = {}
    owners = {}
    for section in spec.sections:
        candidates = [v for v in views if (v['sheet'] == section.sheet if section.sheet is not None
                      else v['sheet'] is None and v['page'] in section.pages)]
        at = {v['id']:i for i,v in enumerate(candidates)}
        if section.line_ids is not None:
            if section.start_line is not None or section.end_line is not None:
                raise ValueError(f'{section.name}: use line_ids or a line range, not both')
            missing = set(section.line_ids) - at.keys()
            if missing:
                raise ValueError(f'{section.name}: unknown/out-of-section lines {sorted(missing)}')
            wanted = set(section.line_ids)
            chosen = [v for v in candidates if v['id'] in wanted]
        elif section.start_line is not None or section.end_line is not None:
            if section.start_line not in at or section.end_line not in at:
                raise ValueError(f'{section.name}: both range endpoints must identify source lines')
            start, end = at[section.start_line], at[section.end_line]
            if start > end:
                raise ValueError(f'{section.name}: reversed section range')
            chosen = candidates[start:end+1]
        else:
            chosen = candidates
        if not chosen:
            raise ValueError(f'{section.name}: section selects no source lines')
        selected[id(section)] = chosen
        for view in chosen:
            owners.setdefault(view['id'], []).append(section)
    for line_id, sections in owners.items():
        if len(sections) < 2:
            continue
        coordinates = set()
        ambiguous = False
        for section in sections:
            explicit = section.line_ids is not None or section.start_line is not None
            fields = {(f.line,f.band) for f in section.fields if f.field != 'ignore'}
            if not explicit or coordinates & fields:
                ambiguous = True
            coordinates.update(fields)
        if ambiguous:
            for section in sections:
                selected[id(section)] = [v for v in selected[id(section)] if v['id'] != line_id]
            diagnostics.append(f'ambiguous section ownership at {line_id}: source line withheld')
    return selected
