"""Fix DynamicTableRegion namespace bug in NWB files.

This module provides a fix for HDMF issue #1347 where DynamicTableRegion and VectorData
types get incorrectly labeled with 'hdmf-experimental' namespace instead of 'hdmf-common'.
This causes MatNWB to fail reading these files.

See: https://github.com/hdmf-dev/hdmf/issues/1347
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import h5py


def _fix_namespace_visitor(name: str, h5obj: Union[h5py.Dataset, h5py.Group]) -> None:
    """Visitor function to fix namespace attributes in HDF5 objects.

    Changes the 'namespace' attribute from 'hdmf-experimental' to 'hdmf-common'
    for DynamicTableRegion and VectorData neurodata types.

    Parameters
    ----------
    name : str
        The name/path of the HDF5 object (unused but required by visititems).
    h5obj : h5py.Dataset or h5py.Group
        The HDF5 object to check and potentially fix.
    """
    if h5obj.attrs.get("namespace") == "hdmf-experimental":
        neurodata_type = h5obj.attrs.get("neurodata_type")
        if neurodata_type in ("DynamicTableRegion", "VectorData"):
            h5obj.attrs["namespace"] = "hdmf-common"


def fix_nwb_namespace(
    nwbfile_path: Union[str, Path],
    logger: logging.Logger | None = None,
) -> int:
    """Fix incorrect namespace attributes in an NWB file.

    This fixes HDMF issue #1347 where DynamicTableRegion and VectorData types
    get incorrectly labeled with 'hdmf-experimental' namespace instead of
    'hdmf-common', which causes MatNWB to fail reading these files.

    Parameters
    ----------
    nwbfile_path : str or Path
        Path to the NWB file to fix.
    logger : logging.Logger, optional
        Logger instance for output messages.

    Returns
    -------
    int
        Number of objects that were fixed.
    """
    nwbfile_path = Path(nwbfile_path)

    if not nwbfile_path.exists():
        if logger:
            logger.warning(f"NWB file not found: {nwbfile_path}")
        return 0

    fixed_count = 0

    def counting_visitor(name: str, h5obj: Union[h5py.Dataset, h5py.Group]) -> None:
        nonlocal fixed_count
        if h5obj.attrs.get("namespace") == "hdmf-experimental":
            neurodata_type = h5obj.attrs.get("neurodata_type")
            if neurodata_type in ("DynamicTableRegion", "VectorData"):
                h5obj.attrs["namespace"] = "hdmf-common"
                fixed_count += 1
                if logger:
                    logger.debug(f"Fixed namespace for: {h5obj.name} ({neurodata_type})")

    with h5py.File(nwbfile_path, "a") as f:
        f.visititems(counting_visitor)

    if logger:
        if fixed_count > 0:
            logger.info(
                f"Fixed {fixed_count} hdmf-experimental -> hdmf-common namespace issue(s) "
                f"in {nwbfile_path.name}"
            )
        else:
            logger.debug(f"No namespace fixes needed in {nwbfile_path.name}")

    return fixed_count
