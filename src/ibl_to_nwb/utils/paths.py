"""Path utilities for IBL-to-NWB conversion."""

import os
import shutil
from pathlib import Path

from one.alf.spec import is_uuid_string
from one.api import ONE


def setup_paths(
    one: ONE,
    eid: str,
    base_path: Path = None,
) -> dict:
    """
    Create a structured dictionary of paths for NWB conversion.

    All paths are derived from base_path:
    - logs_path: base_path/conversion_logs (persistent logs - small, kept for auditing)
    - decompressed_ephys_path: base_path/decompressed_ephys (temporary decompressed ephys files)

    Parameters
    ----------
    one : ONE
        An instance of the ONE API.
    eid : str
        The experiment ID for the session being converted.
    base_path : Path, optional
        The base path for output files. If None, defaults to ~/ibl_bmw_to_nwb.

    Returns
    -------
    dict
        A dictionary containing the following paths:
        - output_folder: Path to store the output NWB files.
        - session_folder: Path to the original session data (ONE cache).
        - logs_folder: Path for conversion logs (persistent).
        - decompressed_ephys_folder: Path for temporary decompressed ephys files.
        - session_decompressed_ephys_folder: Path for this session's ephys files.
        - spikeglx_source_folder: Path to the raw ephys data for this session.
    """
    base_path = Path.home() / "ibl_bmw_to_nwb" if base_path is None else base_path

    # Logs go to a persistent location (derived from base_path)
    logs_path = base_path / "conversion_logs"

    # Decompressed ephys uses fast temporary storage (derived from base_path or environment)
    if "USE_SDSC_ONE" in os.environ:
        decompressed_ephys_path = Path("/scratch")  # on SDSC, a per node /scratch folder exists
    else:
        decompressed_ephys_path = base_path / "decompressed_ephys"

    subject = one.eid2ref(eid)["subject"]
    paths = dict(
        output_folder=base_path / "nwbfiles",
        subject=subject,
        session_folder=one.eid2path(eid),
        logs_folder=logs_path,
        decompressed_ephys_folder=decompressed_ephys_path,
    )

    # Session-specific paths
    paths["session_decompressed_ephys_folder"] = paths["decompressed_ephys_folder"] / eid
    paths["spikeglx_source_folder"] = paths["session_decompressed_ephys_folder"] / "raw_ephys_data"

    # Create base directories
    paths["output_folder"].mkdir(exist_ok=True, parents=True)
    paths["logs_folder"].mkdir(exist_ok=True, parents=True)
    paths["decompressed_ephys_folder"].mkdir(exist_ok=True, parents=True)
    paths["session_decompressed_ephys_folder"].mkdir(exist_ok=True, parents=True)
    paths["spikeglx_source_folder"].mkdir(exist_ok=True, parents=True)

    return paths


def remove_uuid_from_filepath(file_path: Path) -> Path:
    """Remove UUID from filename if present."""
    dir_path, name = file_path.parent, file_path.name
    name_parts = name.split(".")
    if len(name_parts) >= 2 and is_uuid_string(name_parts[-2]):
        name_parts.remove(name_parts[-2])
        return dir_path / ".".join(name_parts)
    return file_path


def filter_file_paths(
    file_paths: list[Path],
    include: list | None = None,
    exclude: list | None = None,
) -> list[Path]:
    """Filter file paths by include/exclude patterns."""
    if include is not None:
        file_paths_ = []
        if not isinstance(include, list):
            include = [include]
        for incl in include:
            file_paths_.extend(f for f in file_paths if incl in f.name)
        file_paths = list(set(file_paths_))

    if exclude is not None:
        if not isinstance(exclude, list):
            exclude = [exclude]
        for excl in exclude:
            file_paths = [f for f in file_paths if excl not in f.name]

    return file_paths


def tree_copy(
    source_dir: Path,
    target_dir: Path,
    remove_uuid: bool = True,
    include: list | None = None,
    exclude: list | None = None,
) -> None:
    """Copy directory tree with optional UUID removal and filtering."""
    file_paths = list(source_dir.rglob("**/*"))
    if include is not None or exclude is not None:
        file_paths = filter_file_paths(file_paths, include, exclude)

    for source_file_path in file_paths:
        if source_file_path.is_file():
            target_file_path = target_dir / source_file_path.relative_to(source_dir)
            if remove_uuid:
                target_file_path = remove_uuid_from_filepath(target_file_path)
            if target_file_path.exists():
                continue

            target_file_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy(source_file_path, target_file_path)
            except FileNotFoundError:
                target_file_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(source_file_path, target_file_path)


def check_camera_health_by_qc(bwm_qc: dict, eid: str, camera_name: str) -> bool:
    """Check camera health from QC data."""
    view = camera_name.split("Camera")[0].capitalize()
    qc = bwm_qc[eid][f"video{view}"]
    return qc not in ["CRITICAL", "FAIL"]
