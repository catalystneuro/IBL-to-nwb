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
        return [stream_name for stream_name in cls.Extractor.get_stream_names(session=session) if "ap" in stream_name]

    def __init__(self, **kwargs):
        self.session = kwargs["session"]
        self.stream_name = kwargs["stream_name"]
        super().__init__(**kwargs)

        self.available_streams = self.get_stream_names(session=self.session)
        if len(self.available_streams) > 1:
            probe_number = self.stream_name[5:7]
            self.es_key = f"ElectricalSeriesAp{probe_number}"
        else:
            self.es_key = "ElectricalSeriesAp"

        one = ONE(base_url="https://openalyx.internationalbrainlab.org", password="international", silent=True)
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
        finally:
            self.recording_extractor.set_property(key="ibl_x", values=ibl_coords[:, 0])
            self.recording_extractor.set_property(key="ibl_y", values=ibl_coords[:, 1])
            self.recording_extractor.set_property(key="ibl_z", values=ibl_coords[:, 2])
            self.recording_extractor.set_property(
                key="location", values=list(channels["acronym"])
            )  # Acronyms are symmetric, do not differentiate hemisphere to be consistent with their usage
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

        return metadata

    def run_conversion(self, **kwargs):
        # The buffer and chunk shapes must be set explicitly for good performance with the streaming
        # Otherwise, the default buffer/chunk shapes might re-request the same data packet multiple times
        chunk_frames = 100 if kwargs.get("stub_test", False) else 30_000
        buffer_frames = 100 if kwargs.get("stub_test", False) else 5 * 30_000
        kwargs.update(
            iterator_opts=dict(
                display_progress=True,
                chunk_shape=(chunk_frames, 16),  # ~1 MB
                buffer_shape=(buffer_frames, 384),  # 100 MB
                progress_bar_options=dict(
                    desc=f"Converting stream '{self.stream_name}' session '{self.session}'...",
                    position=kwargs.get("progress_position", 0),
                ),
            )
        )
        kwargs.update(es_key=self.es_key)
        super().run_conversion(**kwargs)


class IblStreamingLfInterface(IblStreamingApInterface):
    @classmethod
    def get_stream_names(cls, session: str):
        return [stream_name for stream_name in cls.Extractor.get_stream_names(session=session) if "lf" in stream_name]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.es_key = self.es_key.replace("Ap", "Lf")

    def get_metadata_schema(self) -> dict:
        metadata_schema = super().get_metadata_schema()
        metadata_schema["properties"]["Ecephys"]["properties"].update(
            {self.es_key: get_schema_from_hdmf_class(ElectricalSeries)}
        )
        return metadata_schema

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        ecephys_metadata = load_dict_from_file(file_path=Path(__file__).parent.parent / "metadata" / "ecephys.yml")

        metadata["Ecephys"].update({self.es_key: ecephys_metadata["Ecephys"]["ElectricalSeriesLf"]})
        if len(self.available_streams) > 1:
            metadata["Ecephys"][self.es_key].update(name=self.es_key)

        return metadata

    def run_conversion(self, **kwargs):
        # The buffer and chunk shapes must be set explicitly for good performance with the streaming
        # Otherwise, the default buffer/chunk shapes might re-request the same data packet multiple times
        chunk_frames = 100 if kwargs.get("stub_test", False) else 30_000
        buffer_frames = 100 if kwargs.get("stub_test", False) else 5 * 30_000
        kwargs.update(
            iterator_opts=dict(
                display_progress=True,
                chunk_shape=(chunk_frames, 16),  # ~1 MB
                buffer_shape=(buffer_frames, 384),  # 100 MB
                progress_bar_options=dict(desc=f"Converting stream '{self.stream_name}' session '{self.session}'..."),
            )
        )
        kwargs.update(es_key=self.es_key)
        super(IblStreamingApInterface, self).run_conversion(**kwargs)
