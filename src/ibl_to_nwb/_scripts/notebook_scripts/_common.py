"""Common utilities for notebook figure scripts."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend for saving figures
import matplotlib.pyplot as plt

# Default paths for local NWB files
DEFAULT_BASE_PATH = Path("/media/heberto/Expansion/nwbfiles/full")

# Default session for testing
DEFAULT_SESSION_EID = "fa1f26a1-eb49-4b24-917e-19f02a18ac61"
DEFAULT_SUBJECT = "NYU-39"


def get_output_dir() -> Path:
    """Get the output directory for saved figures."""
    return Path(__file__).parent / "output_images"


def save_figure(fig: plt.Figure, name: str, dpi: int = 150) -> Path:
    """Save a figure to the output_images directory.

    Parameters
    ----------
    fig : plt.Figure
        The matplotlib figure to save.
    name : str
        The name of the figure (without extension).
    dpi : int, optional
        Resolution for the saved figure, by default 150.

    Returns
    -------
    Path
        The path to the saved figure.
    """
    output_dir = get_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{name}.png"
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path


def get_default_processed_path() -> Path:
    """Get the default path for processed NWB file.

    Returns
    -------
    Path
        Path to the default processed NWB file.
    """
    return (
        DEFAULT_BASE_PATH
        / f"sub-{DEFAULT_SUBJECT}"
        / f"sub-{DEFAULT_SUBJECT}_ses-{DEFAULT_SESSION_EID}_desc-processed_behavior+ecephys.nwb"
    )


def get_default_raw_path() -> Path:
    """Get the default path for raw NWB file.

    Returns
    -------
    Path
        Path to the default raw NWB file.
    """
    return (
        DEFAULT_BASE_PATH
        / f"sub-{DEFAULT_SUBJECT}"
        / f"sub-{DEFAULT_SUBJECT}_ses-{DEFAULT_SESSION_EID}_desc-raw_ecephys.nwb"
    )


def create_argument_parser(description: str, file_type: str = "processed") -> argparse.ArgumentParser:
    """Create a standard argument parser for the scripts.

    Parameters
    ----------
    description : str
        Description for the script.
    file_type : str, optional
        Type of NWB file ("processed" or "raw"), by default "processed".

    Returns
    -------
    argparse.ArgumentParser
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(description=description)
    default_path = get_default_processed_path() if file_type == "processed" else get_default_raw_path()
    parser.add_argument(
        "nwbfile_path",
        type=str,
        nargs="?",
        default=str(default_path),
        help=f"Path to the {file_type} NWB file (default: {default_path})",
    )
    return parser
