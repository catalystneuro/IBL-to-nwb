# Brain Atlas Hierarchy Guide

This document explains the Allen Brain Atlas CCFv3 hierarchy structure, how brain regions are assigned to electrodes in the IBL pipeline, and provides tutorial scripts for working with brain region data.

## Table of Contents

1. [Allen Brain Atlas Hierarchy Overview](#1-allen-brain-atlas-hierarchy-overview)
2. [Available Mappings and Granularities](#2-available-mappings-and-granularities)
3. [How IBL Assigns Brain Regions](#3-how-ibl-assigns-brain-regions)
4. [Differences Between iblatlas and brainglobe-atlasapi](#4-differences-between-iblatlas-and-brainglobe-atlasapi)
5. [API Reference by Task](#5-api-reference-by-task)
6. [Reference Tables](#6-reference-tables)

---

## 1. Allen Brain Atlas Hierarchy Overview

The Allen Common Coordinate Framework version 3 (CCFv3) organizes mouse brain structures in a hierarchical ontology with **11 levels** (0-10). Each structure has a unique ID, acronym, full name, and parent relationship.

### Level 1: Top-Level Tissue Types

The atlas first divides the brain into 5 fundamental tissue types:

| Acronym | Name | Description | Relevance for Electrophysiology |
|---------|------|-------------|--------------------------------|
| `grey` | Basic cell groups and regions | **Neuronal cell bodies** - where neurons live and process information | Primary interest - all neural recordings come from here |
| `fiber tracts` | fiber tracts | **White matter** - myelinated axon bundles connecting regions | Electrodes passing through white matter (low signal) |
| `VS` | ventricular systems | **Fluid-filled cavities** - contain cerebrospinal fluid | Should not have electrodes here (no neural tissue) |
| `grv` | grooves | **Surface folds** - sulci and fissures on the brain surface | Anatomical landmarks only |
| `retina` | retina | **Sensory tissue** - part of CNS embryologically | Not relevant for brain recordings |

For electrophysiology, you almost exclusively care about **`grey` descendants**. Labels like `fiber tracts`, `VS`, or `root` indicate electrodes outside grey matter or at uncertain locations.

### Hierarchy Levels (Grey Matter Branch)

The following table shows the hierarchy within the `grey` branch - the neural tissue where recordings occur:

| Level | # Regions | Description | Example Regions |
|-------|-----------|-------------|-----------------|
| **0** | 1 | Root | `root` |
| **1** | 1 | Neural tissue | `grey` (Basic cell groups and regions) |
| **2** | 3 | Major brain divisions | `CH` (Cerebrum), `BS` (Brain stem), `CB` (Cerebellum) |
| **3** | 7 | Major subdivisions | `CTX` (Cerebral cortex), `CNU` (Cerebral nuclei), `MB` (Midbrain), `HB` (Hindbrain), `TH` (Thalamus), `HY` (Hypothalamus) |
| **4** | 20 | Major structures | `TH` (Thalamus), `STR` (Striatum), `PAL` (Pallidum), `MY` (Medulla), `P` (Pons) |
| **5** | 77 | Substructures | `Isocortex`, `HPF` (Hippocampal formation), `OLF` (Olfactory areas), `CTXsp` (Cortical subplate) |
| **6** | 251 | Functional areas | `MO` (Somatomotor areas), `SS` (Somatosensory areas), `VIS` (Visual areas), `ACA` (Anterior cingulate) |
| **7** | 324 | Specific areas | `MOp` (Primary motor), `SSp` (Primary somatosensory), `VISp` (Primary visual), `CA1`, `CA3` |
| **8** | 272 | Area subdivisions + layers | `MOp5` (Primary motor layer 5), `SSp-ll` (Somatosensory lower limb) |
| **9** | 139 | Subfield layers | `SSp-n4` (Somatosensory nose layer 4), `VISp2/3` |
| **10** | 6 | Most granular | `VISrll4` (Rostrolateral visual area layer 4) |

**Total grey matter regions**: ~1,100 of the 1,327 total regions in iblatlas

### Level-by-Level Subdivision Rationale

Understanding why each level exists helps you choose the right granularity for your analysis. Below we trace how regions progressively subdivide from Level 4 onward.

#### Level 4 to Level 5: From Gross Anatomy to Functional Organization

Level 4 contains the major anatomical structures visible in gross dissection: `TH` (Thalamus), `STR` (Striatum), `PAL` (Pallidum), `HY` (Hypothalamus), `MY` (Medulla), `P` (Pons), and the cortical plate/subplate distinction.

Level 5 subdivides these into functionally meaningful groups:

- **Cortical plate** (`CTXpl`) splits into `Isocortex` (6-layered cortex), `OLF` (olfactory areas), and `HPF` (hippocampal formation) - each with fundamentally different circuitry and function
- **Thalamus** (`TH`) splits into `DORsm` (sensory-motor cortex related) and `DORpm` (polymodal association cortex related) - reflecting different projection targets
- **Midbrain** subdivides into `MBmot` (motor), `MBsen` (sensory), and `MBsta` (behavioral state) - functional categories rather than just anatomy
- **Hindbrain** structures gain functional subdivisions like `MY-mot`, `MY-sen`, `MY-sat` (motor, sensory, behavioral state)

**Why this matters**: Level 5 is often the best choice for whole-brain analyses because it groups regions by functional similarity rather than just anatomy. The Cosmos mapping uses Level 5 regions as its basis.

#### Level 5 to Level 6: Functional Areas Within Systems

Level 6 decomposes the broad functional systems of Level 5 into specific functional areas:

- **Isocortex** splits into sensory areas (`VIS` - Visual, `AUD` - Auditory, `SS` - Somatosensory), motor areas (`MO` - Somatomotor), and association areas (`ACA` - Anterior cingulate, `RSP` - Retrosplenial, `ORB` - Orbital)
- **Hippocampal formation** gains subfields: `CA` (cornu ammonis), `DG` (dentate gyrus), `SUB` (subiculum), `ENT` (entorhinal cortex)
- **Thalamic nuclei** appear: `ATN` (anterior group), `ILM` (intralaminar), `LAT` (lateral group), `MED` (medial group), `VENT` (ventral group)
- **Basal ganglia** structures emerge: `CP` (Caudoputamen), `ACB` (Nucleus accumbens), `GPe`/`GPi` (Globus pallidus segments)

**Why this matters**: Level 6 is ideal for comparing across functional systems (e.g., "visual vs somatosensory cortex") while still having enough statistical power from pooled neurons.

#### Level 6 to Level 7: Specific Nuclei and Cortical Subdivisions

Level 7 provides the specific named regions that neuroscientists typically reference:

- **Visual areas** (`VIS`) split into `VISp` (primary), `VISl` (lateral), `VISal` (anterolateral), `VISpm` (posteromedial), etc.
- **Somatosensory** (`SS`) becomes `SSp` (primary) and `SSs` (supplemental), with `SSp` further containing body part representations
- **Hippocampus** gains `CA1`, `CA2`, `CA3` - the classic hippocampal subfields with distinct physiology
- **Thalamic groups** become individual nuclei: `VPM` (ventral posteromedial), `VPL` (ventral posterolateral), `LGd` (dorsal lateral geniculate), `MGd` (dorsal medial geniculate)

**Why this matters**: Level 7 is the standard for publication-quality regional comparisons. Most classic neuroscience papers refer to structures at this level (e.g., "VISp", "CA1", "VPM").

#### Level 7 to Level 8: Layers, Subdivisions, and Subnuclei

Level 8 adds anatomical subdivisions within the Level 7 regions:

- **Cortical areas** gain layer designations: `VISp1` through `VISp6a/6b`, `MOp5`, `SSp4`, etc.
- **Somatosensory** subdivides by body part: `SSp-ll` (lower limb), `SSp-ul` (upper limb), `SSp-n` (nose), `SSp-m` (mouth), `SSp-bfd` (barrel field)
- **Thalamic nuclei** gain subdivisions: `LGd-sh` (shell), `LGd-co` (core), `VPM` subdivisions
- **Superior colliculus** layers: `SCop` (optic), `SCsg` (superficial gray), `SCig` (intermediate gray), `SCdg` (deep gray)

**Why this matters**: Level 8 is essential for layer-specific analyses (e.g., comparing superficial vs deep cortical layers) or somatotopic mapping studies. Neuropixels probes span multiple layers, making this level valuable for laminar analysis.

#### Level 8 to Level 9: Body Part + Layer Combinations

Level 9 combines the subdivisions from Level 8:

- **Somatosensory cortex** gains layer-specific body maps: `SSp-ll5` (lower limb layer 5), `SSp-n4` (nose layer 4), `SSp-bfd2/3` (barrel field layers 2/3)
- **Visual cortex** layers within areas: `VISp2/3`, `VISp4`, `VISp5`, `VISp6a`, `VISp6b`
- **Motor cortex** similarly subdivides: `MOp5`, `MOs5`, `MOp6a`

**Why this matters**: Level 9 is the most granular level that's commonly useful. It allows questions like "do layer 5 neurons in barrel cortex respond differently than layer 5 neurons in limb cortex?" Very few analyses require this precision.

#### Level 9 to Level 10: Maximum Granularity

Level 10 contains only 6 regions in the entire atlas, representing the finest subdivisions:

- `VISrll1` through `VISrll6a` - layers of the rostrolateral visual area (a small higher visual area)

**Why this matters**: Level 10 is rarely used. These regions are so small that most experiments won't have enough units to analyze them separately.

### Key Insight: Mixed Granularity in Data

When you retrieve brain region labels from IBL data, they come at **mixed levels** depending on:

1. **Registration precision** - How accurately the probe was localized histologically
2. **Region boundaries** - Some structures have clearer boundaries than others
3. **Electrode position** - Electrodes clearly within a structure get specific labels; those at boundaries may get broader labels

For example, in the same recording you might see:
- `SSp-ll5` (Level 9 - very specific: "Primary somatosensory lower limb layer 5")
- `TH` (Level 4 - broad: "Thalamus")
- `PAG` (Level 6 - mid-level: "Periaqueductal gray")

---

## 2. Available Mappings and Granularities

The IBL provides three pre-defined mappings to control annotation granularity. These mappings were developed specifically for the [Brain-Wide Map project](https://www.internationalbrainlab.com/brainwide-map) and are implemented in the `iblatlas` package.

### Allen (Full Granularity)
- **1,327 regions** (complete Allen CCFv3 ontology)
- Full detail including cortical layers and nuclear subdivisions
- Use when you need maximum anatomical precision
- This is the native Allen Brain Atlas annotation, not an IBL-specific mapping

### Beryl Mapping

**Origin and Purpose**: The Beryl mapping was developed by [Nick Steinmetz](https://www.steinmetzlab.net/) for the IBL Brain-Wide Map project. It provides a curated set of 308 brain regions at a level appropriate for population-level neural analyses.

**What it includes**:
- Major cortical areas without layer subdivisions (e.g., `VISp` instead of `VISp1`, `VISp2/3`, etc.)
- Major nuclei without sub-nuclear divisions (e.g., `LGd` instead of `LGd-sh`, `LGd-co`)
- All grey matter structures relevant for electrophysiology

**What it excludes**:
- Cortical layer subdivisions (layers 1-6a/6b are collapsed to parent area)
- Sub-nuclear divisions (e.g., shell/core of LGd)
- Fiber tracts, pia, and ventricular structures
- Non-neural tissue

**How it works**: Regions are mapped to their "parent node" at the Beryl level. For example:
- `VISp2/3` (Level 9) -> `VISp` (Level 7)
- `SSp-ll5` (Level 9) -> `SSp-ll` (Level 8)
- `LGd-sh` (Level 8) -> `LGd` (Level 7)

**When to use Beryl**:
- Brain-wide analyses comparing across areas
- When you want interpretable region names without layer complexity
- Replicating IBL Brain-Wide Map analyses
- **Recommended as the default for most analyses**

**IBL-specific**: Yes, Beryl is specific to the IBL and is not available in brainglobe-atlasapi or other general-purpose atlas tools.

### Cosmos Mapping

**Origin and Purpose**: Cosmos provides the coarsest meaningful parcellation, dividing the brain into 10-12 major divisions. It was designed for high-level brain-wide summaries and visualizations.

**Regions** (10 neural tissue divisions + root/void):

| Cosmos Region | Full Name | Description |
|---------------|-----------|-------------|
| `Isocortex` | Isocortex | 6-layered neocortex (sensory, motor, association) |
| `OLF` | Olfactory areas | Olfactory bulb, piriform cortex, etc. |
| `HPF` | Hippocampal formation | Hippocampus, dentate gyrus, subiculum, entorhinal |
| `CTXsp` | Cortical subplate | Claustrum, endopiriform, amygdala (non-striatal) |
| `CNU` | Cerebral nuclei | Striatum (caudate, putamen, accumbens) + pallidum |
| `TH` | Thalamus | All thalamic nuclei |
| `HY` | Hypothalamus | All hypothalamic nuclei |
| `MB` | Midbrain | Superior/inferior colliculus, PAG, VTA, SNr, etc. |
| `HB` | Hindbrain | Pons + medulla (all brainstem below midbrain) |
| `CB` | Cerebellum | Cerebellar cortex and nuclei |

**How it works**: All regions are mapped to one of these 10 major divisions:
- `VISp2/3` -> `Isocortex`
- `CA1` -> `HPF`
- `VPM` -> `TH`
- `PAG` -> `MB`
- `CP` -> `CNU`

**When to use Cosmos**:
- High-level brain-wide summaries
- When sample sizes are too small for finer parcellation
- Visualizations showing major brain systems
- Initial exploratory analyses before drilling down

**IBL-specific**: Yes, Cosmos is specific to the IBL and is not available in other atlas tools.

### Mapping Comparison

| Aspect | Allen | Beryl | Cosmos |
|--------|-------|-------|--------|
| **Regions** | 1,327 | 308 | 10 |
| **Cortical layers** | Yes | No | No |
| **Sub-nuclei** | Yes | No | No |
| **Fiber tracts** | Yes | No | No |
| **Typical use** | Laminar analysis | Regional analysis | Brain-wide summary |
| **IBL-specific** | No | Yes | Yes |
| **Available in brainglobe** | Yes | No | No |

### Lateralization

The Allen Brain Atlas assigns each region a unique ID. The IBL extends this with **lateralized IDs** to distinguish left and right hemispheres:

- **Positive IDs**: Right hemisphere (e.g., `+385` = VISp right)
- **Negative IDs**: Left hemisphere (e.g., `-385` = VISp left)

**Important notes**:
- Acronyms remain the same regardless of hemisphere (`VISp` for both left and right)
- Hemisphere is encoded only in the numeric atlas ID
- The IBL NWB files store the signed atlas ID in the `atlas_id` column
- To determine hemisphere, check the sign of the atlas ID

**Lateralized mappings**: Both Beryl and Cosmos have lateralized variants (`Beryl-lr`, `Cosmos-lr`) that preserve hemisphere information. The non-lateralized versions collapse both hemispheres.

```python
from iblatlas.regions import BrainRegions

br = BrainRegions()

# Get lateralized atlas IDs
atlas_id = -385  # VISp left hemisphere

# Non-lateralized mapping (default) - ignores hemisphere
acronym = br.id2acronym(atlas_id, mapping='Beryl')  # Returns "VISp"

# Check hemisphere from atlas_id
hemisphere = "left" if atlas_id < 0 else "right"
print(f"Region: {acronym}, Hemisphere: {hemisphere}")
```

**In NWB files**: The `atlas_id` column in the electrodes table contains signed values indicating hemisphere. The `brain_area` column contains the acronym (hemisphere-agnostic).

---

## 3. How IBL Assigns Brain Regions

### Overview

Brain regions in IBL NWB files come from histology-aligned probe tracks. The assignment pipeline:

1. **Probe insertion** - Physical insertion of Neuropixels probe into brain
2. **Histology processing** - Brain slicing and imaging after experiment
3. **Track tracing** - Manual identification of probe track in tissue
4. **Registration** - Alignment of track to Allen CCFv3 atlas
5. **Channel assignment** - Each electrode channel gets the region at its 3D coordinate
6. **Unit assignment** - Units inherit the region of their max-amplitude electrode

### Histology Quality Levels

Not all probes have equal quality histology. The IBL uses a quality hierarchy:

| Quality | Description | Data Source |
|---------|-------------|-------------|
| `alf` | Best - Final processed files | Pre-computed ALF files with brain locations |
| `resolved` | High - Expert validated | Alyx database, manually reviewed |
| `aligned` | Medium - Pending validation | Alyx database, awaiting review |
| `traced` | Basic - Raw tracing only | Only insertion coordinates, no alignment |
| `None` | No histology data | No tracing exists |

**Only probes with `alf` quality are included in the NWB conversion.**

### How Units Get Brain Regions

```
Electrode coordinates (from histology)
        |
        v
Atlas lookup: coordinate -> region ID
        |
        v
Region ID -> acronym (e.g., "VISp")
        |
        v
Unit inherits region from max-amplitude electrode
```

---

## 4. Differences Between iblatlas and brainglobe-atlasapi

Both libraries provide access to the Allen Mouse Brain Atlas, but they have different design goals and coverage.

### Coverage Comparison

| Aspect | iblatlas | brainglobe-atlasapi |
|--------|----------|---------------------|
| **Total regions** | 1,327 | 840 |
| **Cortical layers** | Yes (e.g., `SSp-ll5`, `MOp6a`) | No |
| **Fiber tracts** | Yes | Partial |
| **Cerebellar layers** | Yes (`CBXmo`, `CBXpu`, `CBXgr`) | No |
| **Olfactory bulb layers** | Yes (`MOBgl`, `MOBgr`, etc.) | No |
| **Cranial nerves** | Yes | Partial |
| **Grooves/ventricles** | Yes | Partial |

### Feature Comparison

| Feature | iblatlas | brainglobe-atlasapi |
|---------|----------|---------------------|
| **Beryl mapping** | Yes (307 regions) | No |
| **Cosmos mapping** | Yes (11 regions) | No |
| **3D meshes** | No | Yes |
| **3D visualization** | Limited (flatmaps) | Yes (via brainrender) |
| **Multiple atlases** | Allen mouse only | 30+ atlases (mouse, rat, zebrafish, etc.) |
| **Coordinate lookup** | Yes | Yes |
| **Hierarchy tree** | Manual traversal | Built-in `atlas.hierarchy` |

### When to Use Each

**Use iblatlas when:**
- Working with IBL data (NWB files, ALF format)
- You need cortical layer-level precision
- You want to use Beryl/Cosmos mappings for grouping
- You need the complete Allen ontology (1,327 regions)

**Use brainglobe-atlasapi when:**
- You need 3D visualization with brainrender
- You're working with multiple species (not just mouse)
- You need mesh data for rendering
- You want a simpler API with built-in hierarchy visualization

### Hierarchy Levels Match

For the 840 common regions, **both APIs report identical hierarchy levels and IDs**. The difference is only in coverage - iblatlas includes 487 additional fine-grained regions that brainglobe excludes.

```python
# Both return the same for common regions:
# VISp: ID=385, Level=7
# TH:   ID=549, Level=4
# CA1:  ID=382, Level=7
```

### Installation

```bash
# iblatlas (part of IBL environment)
pip install iblatlas

# brainglobe-atlasapi
pip install brainglobe-atlasapi
```

---

## 5. API Reference by Task

This section shows how to perform common tasks using both `iblatlas` and `brainglobe-atlasapi`.

### Task 1: Convert Acronym to Full Name

**iblatlas:**
```python
from iblatlas.regions import BrainRegions

br = BrainRegions()

def acronym_to_name(acronym):
    """Convert acronym to full name."""
    idx = br.acronym2index(acronym)[1][0]
    return str(br.name[idx])

print(acronym_to_name("VISp"))  # "Primary visual area"
print(acronym_to_name("CA1"))   # "Field CA1"
print(acronym_to_name("TH"))    # "Thalamus"
```

**brainglobe-atlasapi:**
```python
from brainglobe_atlasapi import BrainGlobeAtlas

atlas = BrainGlobeAtlas("allen_mouse_25um")

def acronym_to_name(acronym):
    """Convert acronym to full name."""
    return atlas.structures[acronym]['name']

print(acronym_to_name("VISp"))  # "Primary visual area"
print(acronym_to_name("CA1"))   # "Field CA1"
print(acronym_to_name("TH"))    # "Thalamus"
```

---

### Task 2: Convert Full Name to Acronym

**iblatlas:**
```python
from iblatlas.regions import BrainRegions
import numpy as np

br = BrainRegions()

def name_to_acronym(name):
    """Convert full name to acronym (case-insensitive partial match)."""
    name_lower = name.lower()
    for i, n in enumerate(br.name):
        if name_lower in str(n).lower():
            return str(br.acronym[i])
    return None

print(name_to_acronym("Primary visual area"))  # "VISp"
print(name_to_acronym("Thalamus"))             # "TH"
print(name_to_acronym("Field CA1"))            # "CA1"
```

**brainglobe-atlasapi:**
```python
from brainglobe_atlasapi import BrainGlobeAtlas

atlas = BrainGlobeAtlas("allen_mouse_25um")

def name_to_acronym(name):
    """Convert full name to acronym (case-insensitive partial match)."""
    name_lower = name.lower()
    for struct_id in atlas.structures.keys():
        s = atlas.structures[struct_id]
        if name_lower in s['name'].lower():
            return s['acronym']
    return None

print(name_to_acronym("Primary visual area"))  # "VISp"
print(name_to_acronym("Thalamus"))             # "TH"
print(name_to_acronym("Field CA1"))            # "CA1"
```

---

### Task 3: Get All Ancestors (Parent Regions)

**iblatlas:**
```python
from iblatlas.regions import BrainRegions
import numpy as np

br = BrainRegions()

def get_ancestors(acronym):
    """Get all ancestors from region to root."""
    idx = br.acronym2index(acronym)[1][0]
    region_id = br.id[idx]
    ancestors_data = br.ancestors(region_id)

    result = []
    seen = set()
    for aid in ancestors_data['id']:
        mask = br.id == aid
        if np.any(mask):
            acr = str(br.acronym[mask][0])
            if acr not in seen:
                seen.add(acr)
                result.append(acr)
    return result

print(get_ancestors("VISp"))
# ['VISp', 'VIS', 'Isocortex', 'CTXpl', 'CTX', 'CH', 'grey', 'root']
```

**brainglobe-atlasapi:**
```python
from brainglobe_atlasapi import BrainGlobeAtlas

atlas = BrainGlobeAtlas("allen_mouse_25um")

def get_ancestors(acronym):
    """Get all ancestors from region to root."""
    return atlas.get_structure_ancestors(acronym)

print(get_ancestors("VISp"))
# ['root', 'grey', 'CH', 'CTX', 'CTXpl', 'Isocortex', 'VIS']
```

---

### Task 4: Get Ancestor at Specific Level

**iblatlas:**
```python
from iblatlas.regions import BrainRegions
import numpy as np

br = BrainRegions()

def get_ancestor_at_level(acronym, target_level):
    """Get ancestor at a specific hierarchy level."""
    idx = br.acronym2index(acronym)[1][0]
    current_level = br.level[idx]

    if current_level <= target_level:
        return acronym

    region_id = br.id[idx]
    for aid in br.ancestors(region_id)['id']:
        mask = br.id == aid
        if np.any(mask):
            ancestor_idx = np.where(mask)[0][0]
            if br.level[ancestor_idx] == target_level:
                return str(br.acronym[ancestor_idx])
    return acronym

print(get_ancestor_at_level("SSp-ll5", 7))  # "SSp-ll"
print(get_ancestor_at_level("SSp-ll5", 6))  # "SS"
print(get_ancestor_at_level("SSp-ll5", 5))  # "Isocortex"
```

**brainglobe-atlasapi:**
```python
from brainglobe_atlasapi import BrainGlobeAtlas

atlas = BrainGlobeAtlas("allen_mouse_25um")

def get_ancestor_at_level(acronym, target_level):
    """Get ancestor at a specific hierarchy level."""
    path = atlas.structures[acronym]['structure_id_path']
    if target_level < len(path):
        ancestor_id = path[target_level]
        return atlas.structures[ancestor_id]['acronym']
    return acronym

print(get_ancestor_at_level("VISp", 3))  # "CTX"
print(get_ancestor_at_level("VISp", 4))  # "CTXpl"
print(get_ancestor_at_level("VISp", 5))  # "Isocortex"
```

---

### Task 5: Get All Descendants (Child Regions)

**iblatlas:**
```python
from iblatlas.regions import BrainRegions

br = BrainRegions()

def get_descendants(acronym):
    """Get all descendant regions."""
    idx = br.acronym2index(acronym)[1][0]
    region_id = br.id[idx]
    descendants_data = br.descendants(region_id)

    result = []
    seen = set()
    for did in descendants_data['id']:
        if did > 0:  # Skip lateralized
            mask = br.id == did
            if mask.any():
                acr = str(br.acronym[mask][0])
                if acr not in seen:
                    seen.add(acr)
                    result.append(acr)
    return result

print(f"Descendants of TH: {len(get_descendants('TH'))} regions")
```

**brainglobe-atlasapi:**
```python
from brainglobe_atlasapi import BrainGlobeAtlas

atlas = BrainGlobeAtlas("allen_mouse_25um")

def get_descendants(acronym):
    """Get all descendant regions."""
    return atlas.get_structure_descendants(acronym)

print(f"Descendants of TH: {len(get_descendants('TH'))} regions")
```

---

### Task 6: Get Hierarchy Level of a Region

**iblatlas:**
```python
from iblatlas.regions import BrainRegions

br = BrainRegions()

def get_level(acronym):
    """Get hierarchy level of a region."""
    idx = br.acronym2index(acronym)[1][0]
    return int(br.level[idx])

print(get_level("root"))  # 0
print(get_level("TH"))    # 4
print(get_level("VISp"))  # 7
```

**brainglobe-atlasapi:**
```python
from brainglobe_atlasapi import BrainGlobeAtlas

atlas = BrainGlobeAtlas("allen_mouse_25um")

def get_level(acronym):
    """Get hierarchy level (length of path - 1)."""
    path = atlas.structures[acronym]['structure_id_path']
    return len(path) - 1

print(get_level("root"))  # 0
print(get_level("TH"))    # 4
print(get_level("VISp"))  # 7
```

---

### Task 7: Convert Between Mappings (Beryl, Cosmos)

**iblatlas only** (brainglobe-atlasapi doesn't have these mappings):

```python
from iblatlas.regions import BrainRegions

br = BrainRegions()

def to_beryl(acronym):
    """Convert to Beryl mapping (removes layers)."""
    idx = br.acronym2index(acronym)[1][0]
    region_id = br.id[idx]
    beryl_id = br.id2id(region_id, mapping='Beryl')
    return br.id2acronym(beryl_id, mapping='Beryl')

def to_cosmos(acronym):
    """Convert to Cosmos mapping (major divisions)."""
    idx = br.acronym2index(acronym)[1][0]
    region_id = br.id[idx]
    cosmos_id = br.id2id(region_id, mapping='Cosmos')
    return br.id2acronym(cosmos_id, mapping='Cosmos')

print(to_beryl("SSp-ll5"))   # "SSp-ll" (layer removed)
print(to_cosmos("SSp-ll5"))  # "Isocortex" (major division)
print(to_cosmos("CA1"))      # "HPF" (Hippocampal formation)
print(to_cosmos("PAG"))      # "MB" (Midbrain)
```

---

### Task 8: Get Region ID from Acronym

**iblatlas:**
```python
from iblatlas.regions import BrainRegions

br = BrainRegions()

def acronym_to_id(acronym):
    """Get Allen atlas ID from acronym."""
    idx = br.acronym2index(acronym)[1][0]
    return int(br.id[idx])

print(acronym_to_id("VISp"))  # 385
print(acronym_to_id("TH"))    # 549
print(acronym_to_id("root"))  # 997
```

**brainglobe-atlasapi:**
```python
from brainglobe_atlasapi import BrainGlobeAtlas

atlas = BrainGlobeAtlas("allen_mouse_25um")

def acronym_to_id(acronym):
    """Get Allen atlas ID from acronym."""
    return atlas.structures[acronym]['id']

print(acronym_to_id("VISp"))  # 385
print(acronym_to_id("TH"))    # 549
print(acronym_to_id("root"))  # 997
```

---

### Task 9: Get Acronym from Region ID

**iblatlas:**
```python
from iblatlas.regions import BrainRegions

br = BrainRegions()

def id_to_acronym(region_id):
    """Get acronym from Allen atlas ID."""
    return br.id2acronym(region_id)

print(id_to_acronym(385))  # "VISp"
print(id_to_acronym(549))  # "TH"
print(id_to_acronym(997))  # "root"
```

**brainglobe-atlasapi:**
```python
from brainglobe_atlasapi import BrainGlobeAtlas

atlas = BrainGlobeAtlas("allen_mouse_25um")

def id_to_acronym(region_id):
    """Get acronym from Allen atlas ID."""
    return atlas.structures[region_id]['acronym']

print(id_to_acronym(385))  # "VISp"
print(id_to_acronym(549))  # "TH"
print(id_to_acronym(997))  # "root"
```

---

### Task 10: Visualize Hierarchy Tree

**iblatlas:**
```python
from iblatlas.regions import BrainRegions

br = BrainRegions()

def print_subtree(acronym, indent=0, max_depth=3):
    """Print hierarchy subtree."""
    idx = br.acronym2index(acronym)[1][0]
    region_id = br.id[idx]
    level = br.level[idx]
    name = br.name[idx]

    print("  " * indent + f"{acronym} (L{level}): {name}")

    if indent < max_depth:
        descendants = br.descendants(region_id)
        for did in descendants['id']:
            if did > 0:
                d_idx = (br.id == did).argmax()
                if br.parent[d_idx] == region_id:  # Direct children only
                    d_acr = str(br.acronym[d_idx])
                    print_subtree(d_acr, indent + 1, max_depth)

print_subtree("TH", max_depth=2)
```

**brainglobe-atlasapi:**
```python
from brainglobe_atlasapi import BrainGlobeAtlas

atlas = BrainGlobeAtlas("allen_mouse_25um")

# Built-in tree visualization
print(atlas.hierarchy)

# Or get structures at specific levels
level_3 = atlas.get_structures_at_hierarchy_level("root", 3)
print(f"Level 3 structures: {level_3}")
```

---

## 6. Reference Tables

### Hierarchy Level Summary

| Level | Description | Typical Use Case |
|-------|-------------|------------------|
| 0-2 | Root, tissue types, major divisions | Rarely used directly |
| 3-4 | Major brain structures (TH, HY, STR) | Broad comparisons |
| 5 | Isocortex, HPF, OLF | Regional summaries |
| 6 | Functional areas (SS, MO, VIS) | Area-level analysis |
| 7-8 | Specific areas + layers | Detailed cortical analysis |
| 9-10 | Most granular subdivisions | Specialized studies |

### Common IBL Region Acronyms

| Acronym | Full Name | Level | Cosmos Group |
|---------|-----------|-------|--------------|
| `VISp` | Primary visual area | 7 | Isocortex |
| `SSp` | Primary somatosensory area | 7 | Isocortex |
| `MOp` | Primary motor area | 7 | Isocortex |
| `CA1` | Field CA1 | 7 | HPF |
| `CA3` | Field CA3 | 7 | HPF |
| `DG` | Dentate gyrus | 6 | HPF |
| `TH` | Thalamus | 4 | TH |
| `VPM` | Ventral posteromedial nucleus | 7 | TH |
| `LGd` | Dorsal lateral geniculate | 7 | TH |
| `SC` | Superior colliculus | 5 | MB |
| `PAG` | Periaqueductal gray | 6 | MB |
| `SNr` | Substantia nigra reticular | 7 | MB |
| `CP` | Caudoputamen | 6 | CNU |
| `ACB` | Nucleus accumbens | 6 | CNU |

### API Comparison

| Feature | iblatlas | brainglobe-atlasapi |
|---------|----------|---------------------|
| Total regions | 1,327 | 840 |
| Includes cortical layers | Yes | No |
| Beryl/Cosmos mappings | Yes | No |
| 3D visualization | Limited | Yes (with brainrender) |
| Mesh data | No | Yes |

---

## Further Resources

- [Allen Brain Atlas Ontology Viewer](http://atlas.brain-map.org/atlas?atlas=602630314)
- [IBL Atlas Documentation](https://int-brain-lab.github.io/iblenv/notebooks_external/atlas_working_with_ibllib_atlas.html)
- [BrainGlobe Atlas API](https://brainglobe.info/documentation/brainglobe-atlasapi/index.html)
