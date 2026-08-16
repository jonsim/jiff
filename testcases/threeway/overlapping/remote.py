from __future__ import annotations

REHEARSAL_MINUTES = 90


def call_sheet(cast: list[str]) -> str:
    performers = ", ".join(sorted(cast))
    return f"Performers: {performers}. Call time is {REHEARSAL_MINUTES} minutes early."


CAST = ["Kermit", "Fozzie", "Gonzo", "Animal"]
