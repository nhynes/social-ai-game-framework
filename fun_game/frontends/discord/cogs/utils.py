from typing import Iterable


def paginate(items: Iterable[str], max_chars=4000, prefix: str = "- ") -> list[str]:
    pages: list[str] = []
    current_page: list[str] = []
    current_length = 0

    for item in items:
        formatted_item = f"{prefix}{item}\n"
        if current_length + len(formatted_item) > max_chars:
            pages.append("".join(current_page))
            current_page = [formatted_item]
            current_length = len(formatted_item)
        else:
            current_page.append(formatted_item)
            current_length += len(formatted_item)

    if current_page:
        pages.append("".join(current_page))

    return pages
