from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Performer:
    name: str
    role: str
    dressing_room: str | None = None


def programme(performers: list[Performer]) -> str:
    names = ", ".join(performer.name for performer in performers)
    return f"Tonight at the Muppet Theatre: {names}"


CAST = [
    Performer("Kermit", "host"),
    Performer("Fozzie", "comedian"),
]
