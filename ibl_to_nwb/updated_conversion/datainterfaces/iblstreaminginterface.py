"""Data interface wrapper around the SpikeInterface extractor - also sets atlas information."""
import numpy as np
from neuroconv.datainterfaces.ecephys.baserecordingextractorinterface import (
    BaseRecordingExtractorInterface,
)
from neuroconv.utils import get_schema_from_hdmf_class
from pynwb.ecephys import ElectricalSeries
from one.api import ONE
from brainbox.io.one import SpikeSortingLoader
from ibllib.atlas import AllenAtlas
from ibllib.atlas.regions import BrainRegions


class IblStreamingApInterface(BaseRecordingExtractorInterface):
    ExtractorName = "IblStreamingRecordingExtractor"

    @classmethod
    def get_stream_names(cls, session: str):
        return [stream_name for stream_name in cls.Extractor.get_stream_names(session=session) if "ap" in stream_name]

    def __init__(self, **kwargs):
        self.session = kwargs["session"]
        self.stream_name = kwargs["stream_name"]
        super().__init__(**kwargs)

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
            self.recording_extractor.set_property(key="ibl_x", values=ccf_coords[:, 0])
            self.recording_extractor.set_property(key="ibl_y", values=ccf_coords[:, 1])
            self.recording_extractor.set_property(key="ibl_z", values=ccf_coords[:, 2])
            self.recording_extractor.set_property(
                key="allen_location", values=channels["acronym"]
            )  # Acronyms are symmetric, do not differentiate hemisphere to be consistent with their usage
            self.recording_extractor.set_property(
                key="beryl_location", values=brain_regions.id2acronym(atlas_id=channels["atlas_id"], mapping="Beryl")
            )
            self.recording_extractor.set_property(
                key="cosmos_location", values=brain_regions.id2acronym(atlas_id=channels["atlas_id"], mapping="Cosmos")
            )

    def get_metadata_schema(self) -> dict:
        metadata_schema = super().get_metadata_schema()
        metadata_schema["properties"]["Ecephys"]["properties"].update(
            ElectricalSeriesAp=get_schema_from_hdmf_class(ElectricalSeries)
        )
        return metadata_schema

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        metadata["Ecephys"].update(
            ElectricalSeriesAp=dict(
                name="ElectricalSeriesAp", description="Raw acquisition traces for the high-pass (ap) SpikeGLX data."
            )
        )
        if self.has_histology:
            metadata["Ecephys"].update(
                Electrodes=[
                    dict(
                        name="ibl_x",
                        description="Medio-lateral coordinate relative to Bregma, left negative, in micrometers.",
                    ),
                    dict(
                        name="ibl_y",
                        description="Antero-posterior coordinate relative to Bregma, back negative, in micrometers.",
                    ),
                    dict(
                        name="ibl_z",
                        description="Dorso-ventral coordinate relative to Bregma, ventral negative, in micrometers.",
                    ),
                    dict(
                        name="allen_location",
                        description="Brain region reference in the Allen Mouse Brain Atlas.",
                    ),
                    dict(
                        name="beryl_location",
                        description="Brain region reference in the Allen Mouse Brain Atlas.",
                    ),
                    dict(
                        name="cosmos_location",
                        description="Brain region reference in the Allen Mouse Brain Atlas.",
                    ),
                ]
            )

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
        kwargs.update(es_key="ElectricalSeriesAp")
        super().run_conversion(**kwargs)


class IblStreamingLfInterface(IblStreamingApInterface):
    @classmethod
    def get_stream_names(cls, session: str):
        return [stream_name for stream_name in cls.Extractor.get_stream_names(session=session) if "lf" in stream_name]

    def get_metadata_schema(self) -> dict:
        metadata_schema = super().get_metadata_schema()
        metadata_schema["properties"]["Ecephys"]["properties"].update(
            ElectricalSeriesLf=get_schema_from_hdmf_class(ElectricalSeries)
        )
        return metadata_schema

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()

        metadata["Ecephys"].update(
            ElectricalSeriesLf=dict(
                name="ElectricalSeriesLf", description="Raw acquisition traces for the high-pass (lf) SpikeGLX data."
            )
        )

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
        kwargs.update(es_key="ElectricalSeriesLf")
        super(IblStreamingApInterface, self).run_conversion(**kwargs)
