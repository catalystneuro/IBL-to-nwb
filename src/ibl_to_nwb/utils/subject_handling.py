"""Utilities for handling subject IDs in DANDI-compliant format."""


def sanitize_subject_id_for_dandi(subject_id: str) -> str:
    """
    Convert subject ID to DANDI-compliant format for use in filenames and folder names.

    DANDI validation requires that subject IDs in BIDS filenames cannot contain underscores.
    Valid characters are: letters, numbers, and hyphens.

    This function replaces underscores with hyphens to ensure compliance while maintaining
    the structure and readability of the subject ID.

    The original subject ID from the IBL database is preserved in the NWB file's
    Subject.subject_id field for traceability.

    Parameters
    ----------
    subject_id : str
        The original subject ID from the IBL Alyx database (e.g., "DY_013", "NR_0019")

    Returns
    -------
    str
        DANDI-compliant subject ID with underscores replaced by hyphens (e.g., "DY-013", "NR-0019")

    Examples
    --------
    >>> sanitize_subject_id_for_dandi("DY_013")
    'DY-013'
    >>> sanitize_subject_id_for_dandi("NR_0019")
    'NR-0019'
    >>> sanitize_subject_id_for_dandi("MFD_05")
    'MFD-05'
    >>> sanitize_subject_id_for_dandi("SWC042")  # No underscore, unchanged
    'SWC042'

    References
    ----------
    DANDI validation rules: https://github.com/dandi/dandi-cli
    Regex pattern: [^_*\\/<>:|"'?%@;.]+ (no underscores allowed)
    """
    return subject_id.replace("_", "-")
