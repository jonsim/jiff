from __future__ import annotations

REHEARSAL_MINUTES = 30


def call_sheet(cast: list[str]) -> str:
    performers = ", ".join(cast)
    return f"Cast: {performers}. Rehearsal: {REHEARSAL_MINUTES} minutes."


CAST = ["Kermit", "Fozzie", "Gonzo"]
