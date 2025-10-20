from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

from zoneinfo import ZoneInfo

from neuroconv import ConverterPipe
from neuroconv.tools import configure_and_write_nwbfile
from ndx_ibl import IblSubject
from ndx_ibl_bwm import ibl_bwm_metadata
from one.api import ONE
from pynwb import NWBFile, read_nwb

from ..bwm_to_nwb import (
    BrainwideMapConverter,
    decompress_ephys_cbins,
    setup_paths,
    tree_copy,
)
from ..converters import IblSpikeGlxConverter
from ..datainterfaces import IblAnatomicalLocalizationInterface, RawVideoInterface
from ..utils import add_probe_electrodes_with_localization


def _valid_existing_nwb(nwb_path: Path, overwrite: bool, logger: logging.Logger | None = None) -> bool:
    if overwrite or not nwb_path.exists():
        return False

    try:
        read_nwb(str(nwb_path))
    except Exception as exc:
        if logger:
            logger.warning(
                "Existing NWB at %s failed validation (reason: %s); regenerating.",
                nwb_path,
                exc,
            )
        return False

    if logger:
        logger.info("Skipping conversion because %s already exists and is readable.", nwb_path)
    return True


def convert_raw_session(
    eid: str,
    one: ONE,
    stub_test: bool = False,
    stub_include_ecephys: bool = False,
    revision: str | None = None,
    base_path: Path | None = None,
    scratch_path: Path | None = None,
    logger: logging.Logger | None = None,
    overwrite: bool = False,
    redecompress_ephys: bool = False,
) -> dict:
    """Convert IBL raw session to NWB."""

    if logger:
        logger.info(f"Starting RAW conversion for session {eid}")

    # Setup paths
    start_time = time.time()
    paths = setup_paths(one, eid, base_path=base_path, scratch_path=scratch_path)
    if logger:
        logger.info(f"Paths setup completed in {time.time() - start_time:.2f}s")

    session_info = one.alyx.rest("sessions", "read", id=eid)
    subject_nickname = session_info.get("subject")
    if isinstance(subject_nickname, dict):
        subject_nickname = subject_nickname.get("nickname") or subject_nickname.get("name")
    if not subject_nickname:
        subject_nickname = "unknown"

    output_dir = Path(paths["output_folder"]) / ("stub" if stub_test else "full")
    output_dir.mkdir(parents=True, exist_ok=True)
    provisional_nwbfile_path = output_dir / f"sub-{subject_nickname}_ses-{eid}_desc-raw_ecephys.nwb"

    if _valid_existing_nwb(provisional_nwbfile_path, overwrite=overwrite, logger=logger):
        size_bytes = provisional_nwbfile_path.stat().st_size
        size_gb = size_bytes / (1024**3)
        return {
            "nwbfile_path": provisional_nwbfile_path,
            "nwb_size_bytes": size_bytes,
            "nwb_size_gb": size_gb,
            "write_time": 0.0,
            "skipped": True,
        }

    # Get probe insertion IDs
    insertions = one.alyx.rest("insertions", "list", session=eid)
    pname_pid_map = {ins["name"]: ins["id"] for ins in insertions}

    scratch_ephys_folder = paths["session_scratch_folder"] / "raw_ephys_data"
    existing_bins = (
        scratch_ephys_folder.exists() and next(scratch_ephys_folder.rglob("*.bin"), None) is not None
    )

    include_stub_ephys = stub_test and stub_include_ecephys
    include_ecephys = (not stub_test) or include_stub_ephys

    if include_stub_ephys and not existing_bins and not redecompress_ephys:
        include_ecephys = False
        if logger:
            logger.info(
                "Stub mode requested Neuropixels data but no decompressed binaries found in %s; "
                "skipping SpikeGLX interfaces. Use REDECOMPRESS_EPHYS=True to regenerate or run a "
                "non-stub conversion first.",
                scratch_ephys_folder,
            )

    # ========================================================================
    # STEP 1: Decompress raw ephys data
    # ========================================================================
    if include_ecephys:
        if logger:
            logger.info("Preparing raw ephys data on scratch...")
        decompress_start = time.time()

        bins_available = existing_bins

        if scratch_ephys_folder.exists() and redecompress_ephys:
            if logger:
                logger.info(
                    "REDECOMPRESS_EPHYS is True - removing existing decompressed data at %s",
                    scratch_ephys_folder,
                )
            shutil.rmtree(scratch_ephys_folder)
            scratch_ephys_folder.mkdir(parents=True, exist_ok=True)
            bins_available = False

        if bins_available:
            if logger:
                logger.info(
                    "Reusing existing decompressed Neuropixels data from %s (set REDECOMPRESS_EPHYS=True to refresh).",
                    scratch_ephys_folder,
                )
        else:
            if logger:
                logger.info("Decompressing .cbin files...")
            decompress_ephys_cbins(paths["session_folder"], paths["session_scratch_folder"])
            bins_available = True

        # Decompress .cbin files from ONE cache to scratch folder
        # Copy metadata files (.meta, .ch, etc.) to scratch folder
        if logger:
            logger.info("Copying metadata files...")
        tree_copy(
            paths["session_folder"] / "raw_ephys_data",
            paths["session_scratch_folder"] / "raw_ephys_data",
            exclude=".cbin",
        )

        decompress_time = time.time() - decompress_start
        if logger:
            logger.info(f"Scratch data preparation completed in {decompress_time:.2f}s")
    else:
        if logger:
            logger.info("Stub test mode active: skipping raw ephys decompression")

    # ========================================================================
    # STEP 2: Define data interfaces
    # ========================================================================
    if logger:
        logger.info("Creating data interfaces...")
    interface_creation_start = time.time()

    data_interfaces = []

    spikeglx_converter = None
    if include_ecephys:
        # SpikeGLX converter
        spikeglx_converter = IblSpikeGlxConverter(
            folder_path=str(paths["spikeglx_source_folder"]),
            one=one,
            eid=eid,
            pname_pid_map=pname_pid_map,
            revision=revision,
        )
        data_interfaces.append(spikeglx_converter)
    elif stub_test and not stub_include_ecephys:
        if logger:
            logger.info("Stub test mode active (without ephys): skipping SpikeGLX converter setup")
    elif logger:
        logger.info("SpikeGLX data not available: skipping SpikeGLX converter setup (see message above for details)")

    # Anatomical localization
    if pname_pid_map:
        anat_interface = IblAnatomicalLocalizationInterface(
            one=one,
            eid=eid,
            pname_pid_map=pname_pid_map,
            revision=revision,
        )
        data_interfaces.append(anat_interface)
        if not include_ecephys and logger:
            logger.info("Stub mode active: using metadata-only electrodes for anatomical localization")

    # Raw video interfaces (skip in stub mode to avoid large downloads)
    if not stub_test:
        metadata_retrieval = BrainwideMapConverter(one=one, session=eid, data_interfaces=[], verbose=False)
        subject_id = metadata_retrieval.get_metadata()["Subject"]["subject_id"]

        pose_estimation_files = one.list_datasets(eid=eid, filename="*.dlc*")
        for pose_estimation_file in pose_estimation_files:
            camera_name = pose_estimation_file.replace("alf/_ibl_", "").replace(".dlc.pqt", "")
            video_interface = RawVideoInterface(
                nwbfiles_folder_path=base_path,
                subject_id=subject_id,
                one=one,
                session=eid,
                camera_name=camera_name,
                revision=revision,
            )
            data_interfaces.append(video_interface)
    elif logger:
        logger.info("Stub test mode active: skipping raw video interfaces")

    interface_creation_time = time.time() - interface_creation_start
    if logger:
        logger.info(f"Data interfaces created in {interface_creation_time:.2f}s")

    # ========================================================================
    # STEP 3: Create converter
    # ========================================================================
    converter = ConverterPipe(data_interfaces=data_interfaces)

    # ========================================================================
    # STEP 4: Get metadata
    # ========================================================================
    metadata = converter.get_metadata()
    nwbfile_metadata = metadata.setdefault("NWBFile", {})
    subject_metadata_block = metadata.setdefault("Subject", {})

    # Add IBL-specific metadata
    (session_metadata,) = one.alyx.rest(url="sessions", action="list", id=eid)
    (lab_metadata,) = one.alyx.rest("labs", "list", name=session_metadata["lab"])

    # Session metadata
    session_start_time = datetime.fromisoformat(session_metadata["start_time"])
    tzinfo = ZoneInfo(lab_metadata["timezone"])
    session_start_time = session_start_time.replace(tzinfo=tzinfo)

    nwbfile_metadata["session_start_time"] = session_start_time
    nwbfile_metadata["session_id"] = session_metadata["id"]
    nwbfile_metadata["lab"] = lab_metadata.get("name", session_metadata["lab"])
    nwbfile_metadata["institution"] = lab_metadata.get("institution")
    if session_metadata.get("task_protocol"):
        nwbfile_metadata["protocol"] = session_metadata["task_protocol"]

    # Subject metadata
    subject_metadata_list = one.alyx.rest("subjects", "list", nickname=session_metadata["subject"])
    subject_metadata = subject_metadata_list[0]

    subject_metadata_block["subject_id"] = subject_metadata["nickname"]
    subject_metadata_block["sex"] = subject_metadata["sex"]
    subject_metadata_block["species"] = subject_metadata_block.get("species", "Mus musculus")
    if subject_metadata.get("reference_weight"):
        subject_metadata_block["weight"] = subject_metadata["reference_weight"] * 1e-3
    date_of_birth = datetime.strptime(subject_metadata["birth_date"], "%Y-%m-%d")
    subject_metadata_block["date_of_birth"] = date_of_birth.replace(tzinfo=tzinfo)

    for ibl_key, nwb_name in [
        ("last_water_restriction", "last_water_restriction"),
        ("remaining_water", "remaining_water_ml"),
        ("expected_water", "expected_water_ml"),
        ("url", "url"),
    ]:
        if ibl_key in subject_metadata and subject_metadata[ibl_key] is not None:
            subject_metadata_block[nwb_name] = subject_metadata[ibl_key]

    # ========================================================================
    # STEP 5: Configure conversion options
    # ========================================================================
    conversion_options = {}

    # Apply stub_test to SpikeGLX interfaces and enable progress bars
    if include_ecephys and spikeglx_converter is not None:
        spikeglx_options = {}
        for interface_name in spikeglx_converter.data_interface_objects.keys():
            spikeglx_options[interface_name] = {
                "stub_test": stub_test,
                "iterator_options": {
                    "display_progress": True,
                    "progress_bar_options": {"desc": f"Writing {interface_name}"},
                },
            }
        conversion_options["IblSpikeGlxConverter"] = spikeglx_options

    # ========================================================================
    # STEP 6: Create NWBFile and add data
    # ========================================================================
    if logger:
        logger.info("Creating NWBFile and adding data...")
    conversion_start = time.time()

    subject_metadata_for_ndx = metadata.pop("Subject")
    ibl_subject = IblSubject(**subject_metadata_for_ndx)

    nwbfile = NWBFile(**metadata["NWBFile"])
    nwbfile.subject = ibl_subject
    nwbfile.add_lab_meta_data(lab_meta_data=ibl_bwm_metadata(revision=revision))

    if pname_pid_map:
        if logger:
            if include_ecephys:
                logger.info(
                    "Pre-populating electrode table from anatomical localization before SpikeGLX data."
                )
            else:
                logger.info("Adding Neuropixels electrodes from metadata (stub mode)...")
        for probe_name, pid in pname_pid_map.items():
            add_probe_electrodes_with_localization(
                nwbfile=nwbfile,
                one=one,
                eid=eid,
                probe_name=probe_name,
                pid=pid,
                revision=revision,
            )

    # Add data from all interfaces
    for interface_name, data_interface in converter.data_interface_objects.items():
        interface_conversion_options = conversion_options.get(interface_name, {})
        data_interface.add_to_nwbfile(nwbfile=nwbfile, metadata=metadata, **interface_conversion_options)

    conversion_time = time.time() - conversion_start
    if logger:
        logger.info(f"Data conversion completed in {conversion_time:.2f}s")

    # ========================================================================
    # STEP 7: Write NWB file
    # ========================================================================
    if logger:
        logger.info("Writing NWB file...")
    write_start = time.time()

    subject_id = nwbfile.subject.subject_id
    nwbfile_path = output_dir / f"sub-{subject_id}_ses-{eid}_desc-raw_ecephys.nwb"

    configure_and_write_nwbfile(
        nwbfile=nwbfile,
        nwbfile_path=nwbfile_path,
        backend="hdf5",
    )

    write_time = time.time() - write_start

    # Get NWB file size
    nwb_size_bytes = nwbfile_path.stat().st_size
    nwb_size_gb = nwb_size_bytes / (1024**3)

    if logger:
        logger.info(f"NWB file written in {write_time:.2f}s")
        logger.info(f"RAW NWB file size: {nwb_size_gb:.2f} GB ({nwb_size_bytes:,} bytes)")
        logger.info(f"Write speed: {nwb_size_gb / (write_time / 3600):.2f} GB/hour")
        logger.info(f"RAW conversion total time: {time.time() - start_time:.2f}s")
        logger.info(f"RAW conversion completed: {nwbfile_path}")
        logger.info(f"RAW NWB saved to: {nwbfile_path}")

    return {
        "nwbfile_path": nwbfile_path,
        "nwb_size_bytes": nwb_size_bytes,
        "nwb_size_gb": nwb_size_gb,
        "write_time": write_time,
    }
