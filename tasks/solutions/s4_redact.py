import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")


def redact(text):
    return PHONE.sub("[PHONE]", EMAIL.sub("[EMAIL]", text))
