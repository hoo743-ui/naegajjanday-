"""Korean particles that follow the word: "황남빵을", "커피를" — never "황남빵을(를)"."""

from __future__ import annotations


def has_batchim(word: str) -> bool | None:
    """Whether the last syllable ends in a consonant; None when the word does not end in Hangul."""
    last = word.strip()[-1:]
    if not ("가" <= last <= "힣"):
        return None
    return (ord(last) - ord("가")) % 28 != 0


def obj(word: str) -> str:
    """word + 을/를 (a name ending in Latin or a digit keeps both: "CGV을(를)")."""
    batchim = has_batchim(word)
    return f"{word}{'을(를)' if batchim is None else '을' if batchim else '를'}"
