"""Helpers for extracting Article release labels from rendered HTML markup."""

from __future__ import annotations

from html.parser import HTMLParser


_NON_RENDERED_TAGS = {"head", "script", "style", "template"}
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}


def _is_hidden(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
    if tag in _NON_RENDERED_TAGS:
        return True
    attributes = {name.lower(): value for name, value in attrs}
    if "hidden" in attributes or "inert" in attributes:
        return True
    if (attributes.get("aria-hidden") or "").strip().lower() == "true":
        return True
    style = attributes.get("style") or ""
    declarations = {
        name.strip().lower(): value.strip().lower()
        for declaration in style.split(";")
        if ":" in declaration
        for name, value in [declaration.split(":", 1)]
    }
    return (
        declarations.get("display") == "none"
        or declarations.get("visibility") in {"hidden", "collapse"}
        or declarations.get("content-visibility") == "hidden"
    )


class _VisibleMarkupParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self.hidden_stack or _is_hidden(tag, attrs):
            if tag not in _VOID_TAGS:
                self.hidden_stack.append(tag)
            return
        self.parts.append(self.get_starttag_text())

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.hidden_stack and not _is_hidden(tag.lower(), attrs):
            self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.hidden_stack:
            for index in range(len(self.hidden_stack) - 1, -1, -1):
                if self.hidden_stack[index] == tag:
                    del self.hidden_stack[index:]
                    break
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.hidden_stack:
            self.parts.append(data)


def visible_html_markup(raw: str) -> str:
    """Remove comments and non-rendered/explicitly hidden regions from HTML."""
    parser = _VisibleMarkupParser()
    parser.feed(raw)
    parser.close()
    return "".join(parser.parts)
