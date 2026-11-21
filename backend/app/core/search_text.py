"""Shared Unicode normalization for stored and queried lexical search terms."""
import re
import unicodedata


def words(text):
    normalized = "".join(char for char in unicodedata.normalize("NFKD", text.casefold())
                         if unicodedata.category(char) not in {"Mn", "Cf"})
    return {word[:-1] if len(word) > 3 and word.endswith("s") else word
            for word in re.findall(r"\w+", normalized)}


def normalized_search_text(text):
    # Padding lets SQL match complete words with the same token boundaries as Python.
    return " " + " ".join(sorted(words(text))) + " "
