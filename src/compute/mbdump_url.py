"""Resolve the current MusicBrainz full-export URL at runtime.

MetaBrainz publishes a new full export every few days and deletes older ones,
so a pinned snapshot path stops working without warning. Both dump scripts had
`.../fullexport/20260704-002053/mbdump.tar.bz2` hardcoded, which now 404s: any
re-run would have failed at the download with no clue why.

`/fullexport/LATEST` is a one-line pointer to the current snapshot directory,
so resolving through it keeps the scripts working as exports rotate.
"""

from __future__ import annotations

import requests

BASE = "https://data.metabrainz.org/pub/musicbrainz/data/fullexport"


def latest_snapshot(timeout: int = 30) -> str:
    """Return the current snapshot id, e.g. '20260815-002140'."""
    response = requests.get(f"{BASE}/LATEST", timeout=timeout)
    response.raise_for_status()
    snapshot = response.text.strip()
    if not snapshot:
        raise RuntimeError(f"{BASE}/LATEST was empty")
    return snapshot


def dump_url(archive: str = "mbdump.tar.bz2", timeout: int = 30) -> str:
    """URL of `archive` inside the current export.

    archive is 'mbdump.tar.bz2' (7.4 GB: recording, track, medium, release) or
    'mbdump-derived.tar.bz2' (510 MB: release_group_meta, which carries
    first_release_date_year).
    """
    return f"{BASE}/{latest_snapshot(timeout=timeout)}/{archive}"
