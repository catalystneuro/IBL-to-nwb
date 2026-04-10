"""Fixtures module for IBL-to-NWB conversion.

This module provides pre-computed lookup tables and metadata
for fast, offline operation during conversions.
"""

from .load_fixtures import (
    load_bwm_df,
    load_bwm_histology_qc,
    load_bwm_units_df,
    get_probe_name_to_probe_id_dict,
)

__all__ = [
    "load_bwm_df",
    "load_bwm_histology_qc",
    "load_bwm_units_df",
    "get_probe_name_to_probe_id_dict",
]
