"""Data interface wrapper around the SpikeInterface extractor - also sets atlas information."""
from pathlib import Path

import numpy as np
from brainbox.io.one import SpikeSortingLoader
from ibllib.atlas import AllenAtlas
from ibllib.atlas.regions import BrainRegions
from neuroconv.datainterfaces.ecephys.baserecordingextractorinterface import (
    BaseRecordingExtractorInterface,
)
from neuroconv.utils import get_schema_from_hdmf_class, load_dict_from_file
from one.api import ONE
from pynwb.ecephys import ElectricalSeries


class IblStreamingApInterface(BaseRecordingExtractorInterface):
    ExtractorName = "IblStreamingRecordingExtractor"

    @classmethod
    def get_stream_names(cls, session: str):
        return [stream_name for stream_name in cls.get_extractor().get_stream_names(session=session) if "ap" in stream_name]

    def __init__(self, **kwargs):
        self.session = kwargs["session"]
        self.stream_name = kwargs["stream_name"]
        super().__init__(**kwargs)

        # Determine es_key and ElectrodeGroup
        self.available_streams = self.get_stream_names(session=self.session)
        if len(self.available_streams) > 1:
            self.probe_number = self.stream_name[5:7]
            self.es_key = f"ElectricalSeriesAp{self.probe_number}"
        else:
            self.es_key = "ElectricalSeriesAp"

        # Remove 'shank' property is all zero
        shank_property = self.recording_extractor.get_property(key="shank")
        if not any(shank_property):
            self.recording_extractor.delete_property(key="shank")

        # Set Atlas info
        one = ONE(
            base_url="https://openalyx.internationalbrainlab.org",
            password="international",
            silent=True,
            cache_dir=kwargs.get("cache_folder", None),
        )
        atlas = AllenAtlas()
        brain_regions = BrainRegions()

        spike_sorting_loader = SpikeSortingLoader(
            eid=self.session, one=one, pname=self.stream_name.split(".")[0], atlas=atlas
        )
        _, _, channels = spike_sorting_loader.load_spike_sorting()

        self.has_histology = False
        if spike_sorting_loader.histology not in ["alf", "resolved"]:
            return
        self.has_histology = True

        ibl_coords = np.empty(shape=(384, 3))
        ibl_coords[:, 0] = channels["x"]
        ibl_coords[:, 1] = channels["y"]
        ibl_coords[:, 2] = channels["z"]

        try:
            ccf_coords = atlas.xyz2ccf(ibl_coords)  # Sometimes this can fail to map and raises an error
            self.recording_extractor.set_property(key="x", values=ccf_coords[:, 0])
            self.recording_extractor.set_property(key="y", values=ccf_coords[:, 1])
            self.recording_extractor.set_property(key="z", values=ccf_coords[:, 2])
        except ValueError as exception:
            if str(exception).endswith("value lies outside of the atlas volume."):
                pass
            else:
                raise exception
        finally:
            self.recording_extractor.set_property(key="ibl_x", values=ibl_coords[:, 0])
            self.recording_extractor.set_property(key="ibl_y", values=ibl_coords[:, 1])
            self.recording_extractor.set_property(key="ibl_z", values=ibl_coords[:, 2])
            self.recording_extractor.set_property(  # SpikeInterface refers to this as 'brain_area'
                key="brain_area", values=list(channels["acronym"])  # NeuroConv remaps to 'location', a required field
            )  # Acronyms are symmetric, do not differentiate hemisphere
            self.recording_extractor.set_property(
                key="beryl_location",
                values=list(brain_regions.id2acronym(atlas_id=channels["atlas_id"], mapping="Beryl")),
            )
            self.recording_extractor.set_property(
                key="cosmos_location",
                values=list(brain_regions.id2acronym(atlas_id=channels["atlas_id"], mapping="Cosmos")),
            )

    def get_metadata_schema(self) -> dict:
        metadata_schema = super().get_metadata_schema()

        metadata_schema["properties"]["Ecephys"]["properties"].update(
            {self.es_key: get_schema_from_hdmf_class(ElectricalSeries)}
        )

        return metadata_schema

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        ecephys_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "metadata" / "ecephys.yml")

        metadata["Ecephys"].update({self.es_key: ecephys_metadata["Ecephys"]["ElectricalSeriesAp"]})
        if len(self.available_streams) > 1:
            metadata["Ecephys"][self.es_key].update(name=self.es_key)
        if self.has_histology:
            metadata["Ecephys"].update(Electrodes=ecephys_metadata["Ecephys"]["Electrodes"])

        # Add custom devices and groups
        if len(self.available_streams) > 1:
            device_name = f"NeuropixelsProbe{self.probe_number}"
            group_name = f"NeuropixelsShank{self.probe_number}"
        else:
            device_name = f"NeuropixelsProbe"
            group_name = f"NeuropixelsShank"
        # set_channel_groups removes probe
        self.recording_extractor.set_property(
            key="group_name", values=np.array([group_name] * self.recording_extractor.get_num_channels())
        )

        metadata["Ecephys"].update(
            Device=[dict(name=device_name, description="A Neuropixels probe.", manufacturer="IMEC")]
        )
        metadata["Ecephys"].update(
            ElectrodeGroup=[
                dict(
                    name=group_name,
                    description="The electrode group on the Neuropixels probe.",
                    location=", ".join(list(np.unique(self.recording_extractor.get_property(key="brain_area")))),
                    device=device_name,
                )
            ]
        )

        return metadata

    def add_to_nwbfile(self, iterator_opts: dict, progress_position: int, **kwargs):
        # The buffer and chunk shapes must be set explicitly for good performance with the streaming
        # Otherwise, the default buffer/chunk shapes might re-request the same data packet multiple times
        chunk_frames = 100 if kwargs.get("stub_test", False) else 30_000
        buffer_frames = 100 if kwargs.get("stub_test", False) else 5 * 30_000
        kwargs.update(
            iterator_opts=dict(
                display_progress=True,
                #chunk_shape=(chunk_frames, 16),  # ~1 MB
                #buffer_shape=(buffer_frames, 384),  # 100 MB
                buffer_gb=0.1,
                progress_bar_options=dict(
                    desc=f"Converting stream '{self.stream_name}' session '{self.session}'...",
                    position=kwargs.get("progress_position", 0),
                ),
            )
        )
        kwargs["iterator_opts"].update(iterator_opts)
        if "progress_position" in kwargs:
            kwargs.pop("progress_position")
        super().add_to_nwbfile(**kwargs)


class IblStreamingLfInterface(IblStreamingApInterface):
    @classmethod
    def get_stream_names(cls, session: str):
        return [stream_name for stream_name in cls.Extractor.get_stream_names(session=session) if "lf" in stream_name]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.es_key = self.es_key.replace("Ap", "Lf")

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()
        metadata["Ecephys"].pop("ElectrodeGroup")

        ecephys_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "metadata" / "ecephys.yml")

        metadata["Ecephys"].update({self.es_key: ecephys_metadata["Ecephys"]["ElectricalSeriesLf"]})
        if len(self.available_streams) > 1:
            metadata["Ecephys"][self.es_key].update(name=self.es_key)

        return metadata
