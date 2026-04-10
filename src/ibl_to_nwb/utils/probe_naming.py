"""Centralized probe naming utilities for IBL-to-NWB conversion.

All probe names originate from IBL API as 'probe00', 'probe01', etc.
This module provides consistent derivation of all related names.
"""

from __future__ import annotations


def get_probe_suffix(ibl_probe_name: str) -> str:
    """Extract numeric suffix from IBL probe name.

    Parameters
    ----------
    ibl_probe_name : str
        The IBL probe name (e.g., 'probe00', 'probe01')

    Returns
    -------
    str
        The numeric suffix (e.g., '00', '01')

    Raises
    ------
    ValueError
        If the probe name doesn't start with 'probe'

    Examples
    --------
    >>> get_probe_suffix('probe00')
    '00'
    >>> get_probe_suffix('probe01')
    '01'
    """
    if not ibl_probe_name.lower().startswith("probe"):
        raise ValueError(f"Invalid IBL probe name: {ibl_probe_name}")
    return ibl_probe_name[5:]


def get_ibl_probe_name(ibl_probe_name: str) -> str:
    """Get the standardized IBL probe name used throughout NWB.

    Parameters
    ----------
    ibl_probe_name : str
        The IBL probe name (e.g., 'probe00', 'probe01')

    Returns
    -------
    str
        The standardized name (e.g., 'Probe00', 'Probe01')

    Examples
    --------
    >>> get_ibl_probe_name('probe00')
    'Probe00'
    >>> get_ibl_probe_name('probe01')
    'Probe01'

    Notes
    -----
    Used for: Device names, electrode group names, trajectory tables,
    anatomical table prefixes, and general identifiers.
    Manufacturer information (IMEC, Neuropixels) is stored in the
    device description and manufacturer fields.
    """
    suffix = get_probe_suffix(ibl_probe_name)
    return f"Probe{suffix}"
