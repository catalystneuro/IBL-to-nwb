"""Utilities for handling NIDQ wiring configuration."""

import logging
from pathlib import Path

from one.api import ONE


_logger = logging.getLogger(__name__)


def load_nidq_wiring(one: ONE, eid: str) -> dict | None:
    """
    Load NIDQ wiring configuration from ONE.

    The wiring.json file documents how behavioral devices are connected to the
    NIDQ board channels (digital and analog). This mapping varies by rig and is
    essential for interpreting NIDQ channel data.

    Parameters
    ----------
    one : ONE
        ONE API instance
    eid : str
        Session ID

    Returns
    -------
    dict or None
        Wiring configuration with keys:
        - 'SYSTEM': System identifier (e.g., '3B')
        - 'SYNC_WIRING_DIGITAL': Dict mapping port pins (P0.0-P0.7) to device names
        - 'SYNC_WIRING_ANALOG': Dict mapping analog inputs (AI0-AI2) to signal sources
        Returns None if wiring file is not available.

    Example
    -------
    >>> wiring = load_nidq_wiring(one, eid)
    >>> print(wiring['SYNC_WIRING_DIGITAL']['P0.0'])  # 'left_camera'
    """
    try:
        wiring = one.load_dataset(
            id=eid,
            dataset='raw_ephys_data/_spikeglx_ephysData_g0_t0.nidq.wiring.json',
            download_only=False
        )
        return wiring
    except Exception as e:
        _logger.warning(f"Could not load NIDQ wiring.json for session {eid}: {e}")
        return None


def create_channel_name_mapping(wiring: dict | None) -> dict[str, str]:
    """
    Create a mapping from SpikeGLX channel IDs to meaningful device names.

    SpikeGLX uses technical channel identifiers (XD0, XD1, XA0, etc.) while
    the wiring.json provides semantic names (left_camera, bpod, etc.). This
    function creates a mapping between them.

    Parameters
    ----------
    wiring : dict or None
        Wiring configuration from load_nidq_wiring()

    Returns
    -------
    dict[str, str]
        Mapping from SpikeGLX channel IDs to device names.
        Example: {'XD0': 'left_camera', 'XD1': 'right_camera', 'XA0': 'bpod'}
        Returns empty dict if wiring is None.

    Notes
    -----
    Digital channel mapping:
    - P0.0 -> XD0 (bit 0 of digital port)
    - P0.1 -> XD1 (bit 1 of digital port)
    - ... up to P0.7 -> XD7

    Analog channel mapping:
    - AI0 -> XA0
    - AI1 -> XA1
    - AI2 -> XA2
    """
    if wiring is None:
        return {}

    channel_mapping = {}

    # Map digital channels (P0.0-P0.7 -> XD0-XD7)
    digital_wiring = wiring.get('SYNC_WIRING_DIGITAL', {})
    for port_pin, device_name in digital_wiring.items():
        # Extract bit number from port pin (e.g., "P0.3" -> 3)
        if port_pin.startswith('P0.'):
            bit_num = port_pin.split('.')[-1]
            channel_id = f'XD{bit_num}'
            channel_mapping[channel_id] = device_name

    # Map analog channels (AI0-AI2 -> XA0-XA2)
    analog_wiring = wiring.get('SYNC_WIRING_ANALOG', {})
    for analog_input, signal_name in analog_wiring.items():
        # Extract channel number from analog input (e.g., "AI0" -> 0)
        if analog_input.startswith('AI'):
            channel_num = analog_input[2:]  # Get number after 'AI'
            channel_id = f'XA{channel_num}'
            channel_mapping[channel_id] = signal_name

    return channel_mapping


def apply_channel_name_mapping(
    channel_ids: list[str],
    channel_mapping: dict[str, str]
) -> list[str]:
    """
    Apply channel name mapping to a list of channel IDs.

    Replaces technical SpikeGLX channel IDs with meaningful device names from
    the wiring configuration. If a channel ID has no mapping, it's kept as-is.

    Parameters
    ----------
    channel_ids : list[str]
        List of SpikeGLX channel IDs (e.g., ['XD0', 'XD1', 'XA0'])
    channel_mapping : dict[str, str]
        Mapping from create_channel_name_mapping()

    Returns
    -------
    list[str]
        List of device names (e.g., ['left_camera', 'right_camera', 'bpod'])
        Unmapped channels keep their original IDs.

    Examples
    --------
    >>> channel_ids = ['XD0', 'XD1', 'XA0', 'XD999']
    >>> mapping = {'XD0': 'left_camera', 'XD1': 'right_camera', 'XA0': 'bpod'}
    >>> apply_channel_name_mapping(channel_ids, mapping)
    ['left_camera', 'right_camera', 'bpod', 'XD999']
    """
    return [channel_mapping.get(ch_id, ch_id) for ch_id in channel_ids]


def enrich_nidq_metadata_with_wiring(metadata: dict, wiring: dict | None) -> dict:
    """
    Add wiring information to NIDQ metadata for documentation.

    Stores the complete wiring configuration in the metadata so it's preserved
    in the NWB file as documentation of the experimental setup.

    Parameters
    ----------
    metadata : dict
        NWB metadata dictionary
    wiring : dict or None
        Wiring configuration from load_nidq_wiring()

    Returns
    -------
    dict
        Updated metadata with wiring information added under 'NIDQ' key

    Notes
    -----
    The wiring information can be stored as:
    - Lab metadata annotations (session-level)
    - Device annotations (NIDQBoard device)
    - TimeSeries descriptions
    """
    if wiring is None:
        return metadata

    # Store wiring as NIDQ-specific metadata
    if 'NIDQ' not in metadata:
        metadata['NIDQ'] = {}

    metadata['NIDQ']['wiring'] = wiring
    metadata['NIDQ']['system'] = wiring.get('SYSTEM', 'Unknown')

    # Create human-readable channel descriptions
    digital_wiring = wiring.get('SYNC_WIRING_DIGITAL', {})
    analog_wiring = wiring.get('SYNC_WIRING_ANALOG', {})

    channel_descriptions = []
    for port_pin, device in digital_wiring.items():
        channel_descriptions.append(f"Digital {port_pin}: {device}")
    for analog_input, signal in analog_wiring.items():
        channel_descriptions.append(f"Analog {analog_input}: {signal}")

    metadata['NIDQ']['channel_descriptions'] = channel_descriptions

    return metadata
