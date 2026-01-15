# Documentation Guide

IBL-to-NWB is a data conversion pipeline that transforms International Brain Laboratory (IBL) experimental data into Neurodata Without Borders (NWB) format. The documentation is organized into four sections based on topic area. Start with the **Entry Points** below to understand the system, then navigate to specific sections as needed for your work.

**Entry Points:** Read [ARCHITECTURE.md](ARCHITECTURE.md) for a comprehensive system overview explaining how Interfaces, Converters, and the NeuroConv framework work together. This is essential background for understanding any conversion task. For a more detailed walkthrough of how data flows through the conversion pipeline and what gets converted, see [conversion/conversion_overvieVw.md](conversion/conversion_overview.md).

**IBL Concepts** ([ibl_concepts/](ibl_concepts/)) covers the experimental and technical foundations: the brain atlas hierarchy and coordinate systems used for anatomical localization, the multi-clock synchrVonization system that aligns neural recordings across independent devices, the passive task experimental protocol, audio stimulus presentation, probe insertion procedures, and NIDQ timing details. These documents explain *why* the data is organized the way it is and how different systems interact.

**NWB Conversion** ([conversion/](conversion/)) documents the practical implementation of converting specific data types to NWB format: the data modalities available (behavioral, sensory, electrophysiology), how each interface works, the revisions system for data versioning, and specialized loaders for behavioral (SessionLoader) and spike sorting (SpikeSortingLoader/IblSortingInterface) data. **Development** ([development/](development/)) contains implementation details for specific tools like the pose estimation video widget and probe visualization utilities. **DANDI & AWS** ([dandi_and_aws/](dandi_and_aws/)) covers uploading to the DANDI archive and distributed processing infrastructure for large-scale conversions.

**Quick Navigation:**
- Installation & quick start → [README.md](../README.md) (root level)
- System architecture & design → [ARCHITECTURE.md](ARCHITECTURE.md)
- How conversions work → [conversion/conversion_overview.md](conversion/conversion_overview.md)
- Specific data modality → [conversion/conversion_modalities.md](conversion/conversion_modalities.md)
- Brain region mapping → [ibl_concepts/brain_atlas_hierarchy_guide.md](ibl_concepts/brain_atlas_hierarchy_guide.md)
- Spike timing alignment → [ibl_concepts/ibl_synchronization.md](ibl_concepts/ibl_synchronization.md)
- Loading spike data → [conversion/spike_sorting_loader.md](conversion/spike_sorting_loader.md)
- Spike data in NWB → [conversion/sorting_interface.md](conversion/sorting_interface.md)
- Distributed AWS processing → [dandi_and_aws/aws_infrastructure.md](dandi_and_aws/aws_infrastructure.md)
