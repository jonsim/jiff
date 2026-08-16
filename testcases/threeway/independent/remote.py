from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Performer:
    name: str
    role: str


def programme(performers: list[Performer]) -> str:
    names = ", ".join(sorted(performer.name for performer in performers))
    return f"Tonight: {names}"


CAST = [
    Performer("Kermit", "host"),
    Performer("Fozzie", "comedian"),
    Performer("Miss Piggy", "diva"),
]
