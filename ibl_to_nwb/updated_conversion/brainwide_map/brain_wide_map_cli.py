
import click
from one.api import ONE

from ibl_to_nwb.updated_conversion.brainwide_map import BrainwideMapConverter
from ibl_to_nwb.updated_conversion.brainwide_map.datainterfaces import (
    BrainwideMapTrialsInterface,
)
from ibl_to_nwb.updated_conversion.datainterfaces import (
    IblStreamingApInterface,
    IblStreamingLfInterface,
)

@click.command()
@click.argument("session")
@click.argument("cache_folder")
@click.option(
    "--preview",
    is_flag=True,
    help=(
        "When 'path' is a six-digit DANDISet ID, this further specifies which version of " "the DANDISet to inspect."
    ),
)
def convert_raw_session_cli(session: str, cache_folder: str, preview: bool = False):
    convert_raw_session(session=session, cache_folder=cache_folder, preview=preview)

def convert_raw_session(session: str, cache_folder: str, preview: bool = False):
    assert len(os.environ.get("DANDI_API_KEY", "")) > 0, "Run `export DANDI_API_KEY=...`!"

    nwbfile_path = cache_folder / "nwbfiles" / session / f"{session}.nwb"
    nwbfile_path.parent.mkdir(exist_ok=True)

    # Download behavior and spike sorted data for this session
    session_one = ONE(
        base_url="https://openalyx.internationalbrainlab.org",
        password="international",
        silent=True,
        cache_dir=cache_folder,
    )

    # Get stream names from SI
    ap_stream_names = IblStreamingApInterface.get_stream_names(session=session)
    lf_stream_names = IblStreamingLfInterface.get_stream_names(session=session)

    # Initialize as many of each interface as we need across the streams
    data_interfaces = list()
    for stream_name in ap_stream_names:
        data_interfaces.append(
            IblStreamingApInterface(
                session=session, stream_name=stream_name, cache_folder=cache_folder / "ap_recordings"
            )
        )
    for stream_name in lf_stream_names:
        data_interfaces.append(
            IblStreamingLfInterface(
                session=session, stream_name=stream_name, cache_folder=cache_folder / "lf_recordings"
            )
        )

    # Run conversion
    session_converter = BrainwideMapConverter(one=session_one, session=session, data_interfaces=data_interfaces)

    conversion_options = dict()
    if preview:
        for data_interface_name in session_converter.data_interface_objects:
            if "Ap" in data_interface_name or "Lf" in data_interface_name:
                conversion_options.update({data_interface_name: dict(stub_test=True)})

    session_converter.run_conversion(
        nwbfile_path=nwbfile_path,
        metadata=session_converter.get_metadata(),
        conversion_options=conversion_options,
        overwrite=True,
    )
