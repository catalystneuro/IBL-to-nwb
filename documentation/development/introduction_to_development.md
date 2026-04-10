# Development Tools and Resources

This section contains technical documentation for developers working on the IBL-to-NWB conversion pipeline: debugging guides, visualization tools, and deep technical details.

## Documents in This Section

### Debugging and Troubleshooting

- [Troubleshooting](troubleshooting.md) - Common issues and their solutions, including ONE API cache problems
- [NIDQ Timing Details](nidq_timing_details.md) - Deep dive into NIDQ availability, synchronization accuracy, and why 1 kHz sampling is sufficient

### Visualization Tools

- [Pose Video Widget](pose_video_widget.md) - Widget for visualizing pose estimation overlaid on video
- [Probe Slice Visualization Guide](probe_slice_visualization_guide.md) - Visualizing probe trajectories on brain atlas slices

### NWB Implementation Details

- [Insertion and Localization Status in NWB](insertion_and_localization_status_nwb.md) - How probe insertion data is represented in NWB files

## Development Workflow

### Running Tests

```bash
# Quick stub test (5 minutes, no large downloads)
python -c "from ibl_to_nwb.conversion import convert_raw_session; \
  convert_raw_session(eid='xxx', one=one, stub_test=True)"

# Validate NWB output
dandi validate /path/to/file.nwb
```

### Code Quality

```bash
ruff check src/            # Linting
black src/                 # Formatting
pre-commit run --all-files # All hooks
```

### Debug Single Session

```bash
python src/ibl_to_nwb/_scripts/_debug_single.py
python src/ibl_to_nwb/_scripts/inspect_single.py
```

## Related Sections

- [NWB Conversion](../conversion/introduction_to_conversion.md) - Conversion architecture
- [Interface Design](../conversion/ibl_data_interface_design.md) - How to add new interfaces
