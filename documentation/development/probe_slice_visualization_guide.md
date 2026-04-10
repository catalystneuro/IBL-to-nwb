# Probe Slice Visualization Guide

This document provides heuristics for choosing the slice position when visualizing probe trajectories in coronal, sagittal, and horizontal views.

## Slice Orientations

| Slice Type | View Direction | Axes Displayed | Best For |
|------------|---------------|----------------|----------|
| **Coronal** | Front-to-back (along AP axis) | Left-Right vs Dorsal-Ventral | Probes inserted vertically from above |
| **Sagittal** | Side view (along ML axis) | Anterior-Posterior vs Dorsal-Ventral | Probes with significant AP angle |
| **Horizontal** | Top-down (along DV axis) | Left-Right vs Anterior-Posterior | Visualizing ML position and spread |

## Choosing the Slice Position

The key question when visualizing a probe trajectory is: **at what position along the slicing axis should we cut?**

Since the probe extends through 3D space, no single 2D slice will capture all electrodes perfectly. The goal is to choose a slice position that passes through or near the probe, providing meaningful anatomical context.

### Recommended Approach: Use the Mean Coordinate

The simplest and most robust approach is to slice at the **mean coordinate** of the probe electrodes along the slicing axis:

```python
# For coronal slice (slicing along AP axis)
slice_position = int(np.mean(bg_x))

# For sagittal slice (slicing along ML axis)
slice_position = int(np.mean(bg_z))

# For horizontal slice (slicing along DV axis)
slice_position = int(np.mean(bg_y))
```

**Why the mean?**
- It centers the slice on the probe's location in that dimension
- For a probe with little spread in that axis, most electrodes will appear on or near the slice
- For a probe with significant spread, the slice shows the midpoint context

### Alternative Approaches

| Approach | When to Use |
|----------|-------------|
| **Mean** | Default choice; works well for most probes |
| **Median** | When there are outlier electrodes (e.g., noise in localization) |
| **Mode** | When electrodes cluster at specific positions |
| **Min/Max** | To show the entry point (dorsal) or tip (ventral) of the probe |

### Understanding Electrode Spread

Before choosing a slice, it helps to understand how much the probe spreads in each dimension:

```python
extent_ap = bg_x.max() - bg_x.min()  # Anterior-Posterior spread
extent_dv = bg_y.max() - bg_y.min()  # Dorsal-Ventral spread
extent_ml = bg_z.max() - bg_z.min()  # Medial-Lateral spread

print(f"AP spread: {extent_ap:.0f} um")
print(f"DV spread: {extent_dv:.0f} um")
print(f"ML spread: {extent_ml:.0f} um")
```

- **Small spread** in a dimension means the probe is roughly aligned perpendicular to that axis, and that slice view will show most electrodes well
- **Large spread** in a dimension means electrodes span a range of positions, and the slice will only show a cross-section

## Coordinate Systems Reference

### Allen CCFv3 / BrainGlobe Coordinates

| Axis | Direction | Range (um) |
|------|-----------|------------|
| X (Axis 0) | Anterior (0) to Posterior | 0 - 13200 |
| Y (Axis 1) | Dorsal/Superior (0) to Ventral/Inferior | 0 - 8000 |
| Z (Axis 2) | Left (0) to Right | 0 - 11400 |

### Slice Indexing

For the `allen_mouse_25um` atlas (25 um resolution):

```python
from brainglobe_atlasapi import BrainGlobeAtlas
atlas = BrainGlobeAtlas("allen_mouse_25um")

# Convert position (um) to slice index
coronal_idx = int(position_ap / atlas.resolution[0])    # ~528 slices
horizontal_idx = int(position_dv / atlas.resolution[1]) # ~320 slices
sagittal_idx = int(position_ml / atlas.resolution[2])   # ~456 slices
```

## Notes

- For angled probe insertions, no single slice will show the full trajectory. The three views together provide a complete picture.
- If the probe appears scattered in all views, check the coordinate conversions or localization quality.
- Coronal slices typically provide the most familiar neuroanatomical context for researchers.
