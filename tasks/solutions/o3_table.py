def render_table(headers, rows):
    cells = [[str(c) for c in row] for row in rows]
    if any(len(r) != len(headers) for r in cells):
        raise ValueError("row length differs from header")
    widths = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(headers)]
    line = lambda vals: "| " + " | ".join(v.ljust(w) for v, w in zip(vals, widths)) + " |"
    out = [line(headers), line(["-" * w for w in widths])] + [line(r) for r in cells]
    return "\n".join(out)
