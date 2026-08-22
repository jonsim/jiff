from __future__ import annotations

REHEARSAL_MINUTES = 45


def call_sheet(cast: list[str]) -> str:
    performers = ", ".join(cast)
    return f"Today's cast: {performers}. Rehearsal lasts {REHEARSAL_MINUTES} minutes."


CAST = ["Kermit", "Gonzo"]
