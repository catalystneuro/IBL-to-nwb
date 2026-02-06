"""tqdm patching utilities.

This module has NO heavy imports (no ONE, spikeglx, mtscomp, etc.) so it can
be safely imported and called BEFORE any library that uses tqdm. This is critical
for the AWS pipeline where disable_tqdm_globally() must patch tqdm.std.tqdm
before the import chain (ONE -> tqdm, spikeglx -> mtscomp -> tqdm) caches
references to the original class.
"""

from __future__ import annotations

import os


def disable_tqdm_globally() -> None:
    """Disable all tqdm progress bars by monkey-patching tqdm.std.tqdm.

    The env var TQDM_DISABLE=1 works for well-behaved consumers, but mtscomp
    creates tqdm instances directly and ignores it. This patches the tqdm class
    itself so that *all* progress bars are force-disabled.

    IMPORTANT: Must be called BEFORE importing any library that does
    ``from tqdm import tqdm`` (e.g. ONE, spikeglx, mtscomp), otherwise those
    modules will have cached a reference to the original unpatched class.

    Safe to call multiple times (idempotent).
    """
    os.environ["TQDM_DISABLE"] = "1"

    import tqdm.std

    # Guard against double-patching
    if getattr(tqdm.std.tqdm, "_ibl_disabled", False):
        return

    _original_tqdm = tqdm.std.tqdm

    class _DisabledTqdm(_original_tqdm):
        _ibl_disabled = True

        def __init__(self, *args, **kwargs):
            kwargs["disable"] = True
            super().__init__(*args, **kwargs)

    tqdm.std.tqdm = _DisabledTqdm
    tqdm.tqdm = _DisabledTqdm
