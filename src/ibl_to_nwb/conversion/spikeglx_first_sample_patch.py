"""Temporary workaround for missing ``firstSample`` in old SpikeGLX meta files.

One IBL session (ibl_witten_13 from wittenlab, recorded 2019-12-03) was acquired
with SpikeGLX ``appVersion=20190413`` (Phase 3A, Imec API v4.3). The ``.meta``
files lack the ``firstSample`` field entirely, even though it is documented in
all SpikeGLX metadata guides (3A through latest). Some older SpikeGLX builds did
not always write it.

Neo's ``spikeglxrawio.py`` unconditionally reads ``info["meta"]["firstSample"]``
(line 277), causing a ``KeyError``. SpikeGLX's own C++ code
(``DataFile::firstCt()``) defaults to 0 when the field is absent, and old
recordings without this field are always single-file (multi-disk splitting was
only added in 2020), so the first sample is always sample 0.

The proper fix is in neo (use ``.get("firstSample", 0)``). This workaround
injects ``firstSample=0`` into meta files that lack it so that conversion can
proceed until the neo fix is released.
"""

from __future__ import annotations

import logging
from pathlib import Path


def inject_missing_first_sample(
    spikeglx_folder: Path,
    logger: logging.Logger,
) -> int:
    """Add ``firstSample=0`` to SpikeGLX .meta files that lack it.

    Scans all ``.meta`` files under *spikeglx_folder*. For each file that does
    not contain a ``firstSample`` key, appends ``firstSample=0``.

    Idempotent: files that already have ``firstSample`` are untouched.

    Returns the number of files patched.
    """
    patched = 0
    for meta_file in spikeglx_folder.rglob("*.meta"):
        text = meta_file.read_text()

        has_first_sample = any(
            line.split("=", 1)[0].rstrip() == "firstSample"
            for line in text.splitlines()
        )
        if has_first_sample:
            continue

        if not text.endswith("\n"):
            text += "\n"
        text += "firstSample=0\n"
        meta_file.write_text(text)
        patched += 1
        logger.warning(
            "Injected missing firstSample=0 into %s (neo workaround)",
            meta_file.name,
        )

    return patched
