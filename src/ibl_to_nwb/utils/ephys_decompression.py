"""Utilities for decompressing SpikeGLX ephys data."""

import shutil
import warnings
from pathlib import Path

import spikeglx
from one.alf.spec import is_uuid_string


def remove_uuid_from_filepath(file_path: Path) -> Path:
    """
    Remove UUID from filepath if present.

    Parameters
    ----------
    file_path : Path
        The file path to process

    Returns
    -------
    Path
        File path with UUID removed (if it was present)
    """
    dir, name = file_path.parent, file_path.name
    name_parts = name.split(".")
    if is_uuid_string(name_parts[-2]):
        name_parts.remove(name_parts[-2])
        return dir / ".".join(name_parts)
    else:
        return file_path


def decompress_ephys_cbins(
    source_folder: Path,
    target_folder: Path | None = None,
    remove_uuid: bool = True
) -> None:
    """
    Decompress SpikeGLX .cbin files to .bin files.

    This function decompresses compressed SpikeGLX ephys data files (.cbin) to
    uncompressed binary files (.bin) for faster data access. It also copies
    associated metadata (.meta) and channel (.ch) files.

    The function suppresses harmless geometry warnings that occur when LF (local
    field potential) meta files lack snsShankMap fields. LF files use default
    Neuropixel geometry which is correct for these recordings.

    Parameters
    ----------
    source_folder : Path
        Root folder containing .cbin files (searches recursively)
    target_folder : Path, optional
        Destination folder for decompressed .bin files. If None, decompresses
        in-place next to .cbin files.
    remove_uuid : bool, default=True
        If True, removes UUID strings from output filenames for cleaner naming

    Notes
    -----
    - Only decompresses files that don't already exist at the target location
    - Preserves directory structure when using target_folder
    - Suppresses spikeglx geometry warnings during decompression (these are
      harmless and occur because LF meta files lack spatial geometry fields)
    """
    # Clean up macOS hidden files from source folder before processing
    # This prevents spikeglx.Reader from encountering ._* AppleDouble files
    import platform
    if platform.system() == "Darwin" and source_folder.exists():
        for hidden_file in source_folder.rglob("._*"):
            hidden_file.unlink()

    # Find all compressed binary files
    cbin_files = list(source_folder.rglob("*.cbin"))
    if len(cbin_files) == 0:
        return  # No files to decompress

    for file_cbin in cbin_files:
        # Determine target path
        if target_folder is not None:
            target_bin = (target_folder / file_cbin.relative_to(source_folder)).with_suffix(".bin")
        else:
            target_bin = file_cbin.with_suffix(".bin")

        target_bin_no_uuid = remove_uuid_from_filepath(target_bin)
        target_bin_no_uuid.parent.mkdir(parents=True, exist_ok=True)

        # Skip if already decompressed
        if not target_bin_no_uuid.exists():
            # Construct exact paths for metadata files instead of globbing
            # This avoids accidentally matching macOS hidden files (._*)
            cbin_path_no_uuid = remove_uuid_from_filepath(file_cbin)
            file_meta = cbin_path_no_uuid.with_suffix(".meta")
            file_ch = cbin_path_no_uuid.with_suffix(".ch")

            # Verify files exist
            if not file_meta.exists():
                raise RuntimeError(
                    f"Required .meta file not found: {file_meta}\n"
                    f"Expected to find metadata file alongside {file_cbin}"
                )
            if not file_ch.exists():
                raise RuntimeError(
                    f"Required .ch file not found: {file_ch}\n"
                    f"Expected to find channel file alongside {file_cbin}"
                )

            # Suppress geometry warning for LF files
            # LF meta files lack snsShankMap but use default NP geometry correctly
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Meta data doesn't have geometry.*returning defaults",
                    category=UserWarning,
                    module="spikeglx"
                )
                # Decompress and copy metadata
                spikeglx.Reader(file_cbin, meta_file=file_meta, ch_file=file_ch).decompress_to_scratch(
                    scratch_dir=target_bin.parent
                )

            # Remove UUID from output filenames if requested
            if remove_uuid:
                shutil.move(target_bin, target_bin_no_uuid)

            # Remove UUID from meta file at target directory
            if target_folder is not None and remove_uuid is True:
                file_meta_target = remove_uuid_from_filepath(target_bin.parent / file_meta.name)
                if not file_meta_target.exists():
                    shutil.move(target_bin.parent / file_meta.name, file_meta_target)
