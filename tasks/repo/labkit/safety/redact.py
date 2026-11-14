def redact(text):
    """Replace email addresses with [EMAIL] and phone numbers with [PHONE].

    A phone number is 10 digits in groups of 3, 3 and 4, optionally preceded
    by "+1", with optional spaces, dots, dashes or parentheses around or
    between the groups, e.g. 555-123-4567, (555) 123 4567, +1 555.123.4567.
    All other text is left unchanged.
    """
    raise NotImplementedError
