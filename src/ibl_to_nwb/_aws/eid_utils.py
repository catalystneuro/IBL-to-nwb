"""Utilities for working with session EIDs and their indices in bwm_session_eids.json."""

import json
from pathlib import Path


def load_session_eids() -> list[str]:
    """Load the list of session EIDs from bwm_session_eids.json.

    Returns
    -------
    list[str]
        List of session EIDs in order.
    """
    json_path = Path(__file__).parent / "tracking_bwm_conversion" / "bwm_session_eids.json"
    if not json_path.exists():
        raise FileNotFoundError(f"Session EIDs file not found: {json_path}")

    with open(json_path) as f:
        data = json.load(f)

    return data["eids"]


def eids_to_indices(eids: list[str]) -> list[int]:
    """Convert a list of EIDs to their indices in bwm_session_eids.json.

    Parameters
    ----------
    eids : list[str]
        List of session EIDs to look up.

    Returns
    -------
    list[int]
        List of indices corresponding to the EIDs, in the same order.

    Raises
    ------
    ValueError
        If any EID is not found in bwm_session_eids.json.
    """
    all_eids = load_session_eids()
    eid_to_index = {eid: i for i, eid in enumerate(all_eids)}

    indices = []
    missing = []
    for eid in eids:
        if eid in eid_to_index:
            indices.append(eid_to_index[eid])
        else:
            missing.append(eid)

    if missing:
        raise ValueError(f"EIDs not found in bwm_session_eids.json: {missing}")

    return indices


def eids_to_ranges(eids: list[str]) -> list[str]:
    """Convert a list of EIDs to optimized range strings for launch_ec2_instances.py.

    This function finds the indices of the given EIDs and groups consecutive
    indices into ranges. The ranges use Python-style slicing (end exclusive).

    Parameters
    ----------
    eids : list[str]
        List of session EIDs to convert.

    Returns
    -------
    list[str]
        List of range strings in "START-END" format (end exclusive).
        Consecutive indices are grouped into single ranges.

    Examples
    --------
    >>> eids_to_ranges(["eid_at_index_6"])
    ['6-7']

    >>> eids_to_ranges(["eid_at_index_6", "eid_at_index_16", "eid_at_index_17"])
    ['6-7', '16-18']

    >>> eids_to_ranges(["eid_at_index_0", "eid_at_index_1", "eid_at_index_2"])
    ['0-3']
    """
    if not eids:
        return []

    indices = eids_to_indices(eids)
    indices_sorted = sorted(indices)

    ranges = []
    start = indices_sorted[0]
    end = start + 1

    for idx in indices_sorted[1:]:
        if idx == end:
            # Consecutive, extend the current range
            end = idx + 1
        else:
            # Gap found, save current range and start new one
            ranges.append(f"{start}-{end}")
            start = idx
            end = idx + 1

    # Save the last range
    ranges.append(f"{start}-{end}")

    return ranges


def index_to_eid(index: int) -> str:
    """Convert an index to its corresponding EID.

    Parameters
    ----------
    index : int
        Index in bwm_session_eids.json.

    Returns
    -------
    str
        The EID at that index.

    Raises
    ------
    IndexError
        If index is out of range.
    """
    all_eids = load_session_eids()
    if index < 0 or index >= len(all_eids):
        raise IndexError(f"Index {index} out of range. Valid range: 0-{len(all_eids)-1}")
    return all_eids[index]
