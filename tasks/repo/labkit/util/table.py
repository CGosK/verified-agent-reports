def render_table(headers, rows):
    """Render a Markdown table with columns padded to their widest cell.

    Cells are converted with str(). Each column's width is the longest of its
    header and cells; the separator row uses that many dashes. Example:

        | name | n  |
        | ---- | -- |
        | a    | 1  |
        | bbb  | 22 |

    Lines are joined with "\\n" and there is no trailing newline. Raise
    ValueError if a row's length differs from the header's.
    """
    raise NotImplementedError
