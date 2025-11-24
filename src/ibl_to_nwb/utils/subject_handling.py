"""Utilities for handling subject IDs and metadata in DANDI-compliant format."""

from datetime import datetime
from zoneinfo import ZoneInfo

from one.api import ONE


def get_ibl_subject_metadata(one: ONE, session_metadata: dict, tzinfo: ZoneInfo) -> dict:
    """
    Extract subject metadata from Alyx database for NWB conversion.

    This function centralizes the subject metadata extraction logic used across
    different conversion workflows (raw, processed, and converter-based).

    Parameters
    ----------
    one : ONE
        ONE API instance for querying Alyx database
    session_metadata : dict
        Session metadata dict from Alyx containing 'subject' field with nickname
    tzinfo : ZoneInfo
        Timezone information for date_of_birth field

    Returns
    -------
    dict
        Subject metadata block ready for NWB file with fields:
        - subject_id: Subject nickname from Alyx
        - sex: Subject sex (M/F/U/O)
        - species: Always "Mus musculus" for IBL subjects
        - weight: Weight in kilograms (converted from grams)
        - date_of_birth: Date of birth with timezone
        - uuid: Alyx database UUID for programmatic queries
        - last_water_restriction: Last water restriction date (if available)
        - remaining_water_ml: Remaining water in ml (if available)
        - expected_water_ml: Expected water in ml (if available)

    Examples
    --------
    >>> from one.api import ONE
    >>> from zoneinfo import ZoneInfo
    >>> one = ONE(base_url='https://openalyx.internationalbrainlab.org')
    >>> session = one.alyx.rest('sessions', 'list', id='some-eid')[0]
    >>> tzinfo = ZoneInfo('America/New_York')
    >>> subject_metadata = get_ibl_subject_metadata(one, session, tzinfo)
    """
    # Query Alyx for subject metadata
    subject_metadata_list = one.alyx.rest("subjects", "list", nickname=session_metadata["subject"])
    subject_metadata = subject_metadata_list[0]

    # Build basic subject metadata block
    subject_block = {
        "subject_id": subject_metadata["nickname"],
        "sex": subject_metadata["sex"],
        "species": "Mus musculus",  # All IBL subjects are mice
    }

    # Add weight if available (convert from grams to kilograms)
    if subject_metadata.get("reference_weight"):
        subject_block["weight"] = subject_metadata["reference_weight"] * 1e-3

    # Add date of birth with timezone
    date_of_birth = datetime.strptime(subject_metadata["birth_date"], "%Y-%m-%d")
    subject_block["date_of_birth"] = date_of_birth.replace(tzinfo=tzinfo)

    # Add IBL-specific extra fields
    for ibl_key, nwb_name in [
        ("last_water_restriction", "last_water_restriction"),
        ("remaining_water", "remaining_water_ml"),
        ("expected_water", "expected_water_ml"),
        ("id", "uuid"),  # Alyx database UUID for programmatic queries
    ]:
        if ibl_key in subject_metadata and subject_metadata[ibl_key] is not None:
            subject_block[nwb_name] = subject_metadata[ibl_key]

    return subject_block


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
