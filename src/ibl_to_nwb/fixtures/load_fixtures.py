import json
from pathlib import Path

import pandas as pd


def load_bwm_df():
    path = Path(__file__).parent / "bwm_df.pqt"
    return pd.read_parquet(path)


def load_bwm_units_df():
    path = Path(__file__).parent / "bwm_units_df.pqt"
    return pd.read_parquet(path)


def load_bwm_qc():
    path = Path(__file__).parent / "bwm_qc.json"
    with open(path, "r") as fH:
        return json.load(fH)


def load_bwm_histology_qc():
    """Load histology QC table as a pandas DataFrame.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns:
        - eid: session ID
        - pid: probe insertion ID
        - probe_name: probe name (e.g., 'probe00')
        - histology_quality: 'alf', 'resolved', 'aligned', 'traced', or None
        - has_histology_files: boolean
        - tracing_exists: boolean
        - alignment_resolved: boolean
        - alignment_count: int
    """
    path = Path(__file__).parent / "bwm_histology_qc.csv"
    return pd.read_csv(path)


def get_probe_name_to_probe_id_dict(eid: str, histology_qc_df: pd.DataFrame = None) -> dict:
    """Extract probe_name_to_probe_id_dict for a session from histology QC table.

    This function provides a fast lookup alternative to querying Alyx REST API.
    Uses the pre-computed histology QC table to get probe insertion IDs.

    Parameters
    ----------
    eid : str
        Session ID
    histology_qc_df : pd.DataFrame, optional
        Pre-loaded histology QC DataFrame. If None, will load automatically.

    Returns
    -------
    dict
        Dictionary mapping probe names to probe insertion IDs (PIDs).
        Example: {'probe00': 'abc-123-def', 'probe01': 'xyz-456-uvw'}

    Examples
    --------
    >>> # Fast lookup from pre-loaded table
    >>> histology_qc_df = load_bwm_histology_qc()
    >>> probe_dict = get_probe_name_to_probe_id_dict(eid, histology_qc_df)

    >>> # Auto-load if needed
    >>> probe_dict = get_probe_name_to_probe_id_dict(eid)
    """
    if histology_qc_df is None:
        histology_qc_df = load_bwm_histology_qc()

    # Filter to this session's probes
    session_probes = histology_qc_df[histology_qc_df["eid"] == eid]

    # Build dict: {probe_name: pid}
    probe_name_to_probe_id_dict = dict(zip(session_probes["probe_name"], session_probes["pid"]))

    return probe_name_to_probe_id_dict
