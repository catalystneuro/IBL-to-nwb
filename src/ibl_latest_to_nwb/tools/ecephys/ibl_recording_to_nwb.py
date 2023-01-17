from typing import Optional

import numpy as np
from brainbox.io.spikeglx import Streamer
from hdmf.backends.hdf5 import H5DataIO
from neuroconv.tools.nwb_helpers import get_module, make_or_load_nwbfile
from neuroconv.utils import OptionalFilePathType
from one.api import ONE
from pynwb import NWBFile
from pynwb.ecephys import LFP, ElectricalSeries

from ibl_latest_to_nwb.tools.ecephys.spikeglxstreamerdatachunkiterator import (
    SpikeGLXStreamerDataChunkIterator,
)
from ibl_latest_to_nwb.tools.one_api.helpers import (
    get_num_probes,
    session_to_probe_id_mapping,
)

IBL_CONFIG = (
    dict()
)  # The credentials dict for the IBL database (to be stored in GitHub secret)


def add_device(file_streamer: Streamer, nwbfile: NWBFile):

    device_name = file_streamer.pname
    if device_name in nwbfile.devices:
        return

    nwbfile.create_device(
        name=device_name,  # 'probe00'
        description=f"Version: {file_streamer.version}",
        # TODO: Where to find the description for this device?
        manufacturer=file_streamer.meta["typeThis"],  # 'imec'
    )


def add_electrodes(file_streamer: Streamer, nwbfile: NWBFile):

    device_name = file_streamer.pname
    device = nwbfile.devices[device_name]
    electrodes_geometry = file_streamer.geometry

    for additional_attribute in [
        "shank_col",
        "shank_row",
        "shank",
        "flag",
        "sample_shift",
        "adc",
        "ind_in_probe",
    ]:
        nwbfile.add_electrode_column(
            name=additional_attribute,
            description="no description.",  # TODO: Add descriptions
        )

    shank_ids = np.unique(electrodes_geometry["shank"]).astype(int)
    for shank_id in shank_ids:
        electrode_group = nwbfile.create_electrode_group(
            name=f"{device_name}_shank{shank_id}",
            description=f"{device_name}_shank{shank_id}",
            location="unknown",  # TODO: access from metadata
            device=device,
        )

        for electrode_ind in range(len(electrodes_geometry["ind"])):
            nwbfile.add_electrode(
                group=electrode_group,
                filtering="unknown",  # TODO: access from metadata (not sure if available)
                imp=None,  # TODO: Where to pull impedance from?
                x=np.nan,
                y=np.nan,
                z=np.nan,
                rel_x=electrodes_geometry["x"][electrode_ind],
                rel_y=electrodes_geometry["y"][electrode_ind],
                rel_z=np.nan,
                shank_col=electrodes_geometry["col"][electrode_ind],
                shank_row=electrodes_geometry["row"][electrode_ind],
                shank=electrodes_geometry["shank"][electrode_ind],
                flag=electrodes_geometry["flag"][electrode_ind],
                sample_shift=electrodes_geometry["sample_shift"][electrode_ind],
                adc=electrodes_geometry["adc"][electrode_ind],
                ind_in_probe=electrodes_geometry["ind"][electrode_ind],
                location="unknown",  # TODO: pull from metadata?
            )


def get_electrodes_mapping(nwbfile: NWBFile):
    return {
        (
            nwbfile.electrodes["group"][idx].device.name,
            nwbfile.electrodes["ind_in_probe"][idx],
        ): idx
        for idx in range(len(nwbfile.electrodes))
    }


def add_electrical_series(
    file_streamer: Streamer,
    probe_index: int,
    nwbfile: Optional[NWBFile] = None,
    stub_test: bool = False,
    iterator_options: Optional[dict] = None,
):

    iterator_options = iterator_options or dict()

    add_device(file_streamer=file_streamer, nwbfile=nwbfile)

    # TODO: fix it for multiple probes
    if nwbfile.electrodes is None:
        add_electrodes(file_streamer=file_streamer, nwbfile=nwbfile)

    modality_signature = "Raw" if file_streamer.type == "ap" else "LFP"
    num_probes = get_num_probes(file_streamer.one, file_streamer.pid)
    segment_signature = "" if num_probes == 1 else probe_index
    default_name = f"ElectricalSeries{modality_signature}{segment_signature}"
    default_description = dict(Raw="Raw acquired data", LFP="Processed data - LFP")

    electrical_series_kwargs = dict(
        name=default_name, description=default_description[modality_signature]
    )
    # Select and/or create module if lfp or processed data is to be stored.
    if modality_signature == "LFP":
        ecephys_module = get_module(
            nwbfile=nwbfile,
            name="ecephys",
            description="Intermediate data from extracellular electrophysiology recordings, e.g., LFP.",
        )
        if modality_signature not in ecephys_module.data_interfaces:
            ecephys_module.add(LFP(name=modality_signature))

    mapping = get_electrodes_mapping(nwbfile=nwbfile)

    electrical_series_iterator = SpikeGLXStreamerDataChunkIterator(
        file_streamer=file_streamer,
        **iterator_options,
    )

    data = (
        electrical_series_iterator
        if not stub_test
        else file_streamer[slice(0, int(10 * file_streamer.fs)), : -file_streamer.nsync]
    )
    rate = file_streamer.fs

    group = file_streamer.pname
    electrical_series_kwargs.update(
        data=H5DataIO(data, compression=True),
        rate=rate,
        starting_time=file_streamer.meta["firstSample"]
        / rate,  # TODO: not sure this is correct. What is "first sample" here?
        # timestamps: is in another file, sure need to check if regular, if so rate is good
        electrodes=nwbfile.create_electrode_table_region(
            name="electrodes",
            description=f"The electrodes used for {modality_signature}.",
            region=[
                mapping[(group, electrode_id)] for electrode_id in nwbfile.electrodes.id
            ],
        ),
    )
    # Create ElectricalSeries object and add it to nwbfile
    electrical_series = ElectricalSeries(**electrical_series_kwargs)

    if file_streamer.type == "ap":
        nwbfile.add_acquisition(electrical_series)
    elif file_streamer.type == "lf":
        ecephys_module.data_interfaces["LFP"].add_electrical_series(electrical_series)


def write_recording(
    session_id: str,
    nwbfile_path: OptionalFilePathType = None,
    nwbfile: Optional[NWBFile] = None,
    metadata: Optional[dict] = None,
    overwrite: bool = False,
    verbose: bool = True,
    stub_test: bool = True,
    compression: Optional[str] = None,
    compression_opts: Optional[int] = None,
    iterator_options: Optional[dict] = None,
):
    with make_or_load_nwbfile(
        nwbfile_path=nwbfile_path,
        nwbfile=nwbfile,
        metadata=metadata,
        overwrite=overwrite,
        verbose=verbose,
    ) as nwbfile_out:

        one = ONE(silent=True, **IBL_CONFIG)

        probe_mapping = session_to_probe_id_mapping(one=one)
        probe_ids = probe_mapping[session_id]

        for probe_index, probe_id in enumerate(probe_ids):
            for type in ["ap", "lf"]:
                file_streamer = Streamer(
                    pid=probe_id, one=one, remove_cached=True, typ=type
                )
                add_electrical_series(
                    file_streamer=file_streamer,
                    probe_index=probe_index,
                    nwbfile=nwbfile_out,
                    stub_test=stub_test,
                    iterator_options=iterator_options,
                )
