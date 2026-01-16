# Pose Video Widget

The pose estimation widget overlays DeepLabCut keypoints directly on streaming video. This is implemented using [anywidget](https://anywidget.dev/), a framework for building Jupyter widgets that work across JupyterLab, Jupyter Notebook, VS Code, and Google Colab.

## How the Widget Works

### 1. Data Preparation (Python side)

Pose estimation coordinates and timestamps are extracted from the NWB file and serialized as JSON for transfer to JavaScript.

```python
# For each keypoint, store coordinates as list of [x, y] or None for missing data
coordinates = {}
for series_name, series in camera_pose.pose_estimation_series.items():
    short_name = series_name.replace("PoseEstimationSeries", "")
    data = series.data[:]  # shape: (n_frames, 2)
    coords_list = []
    for x, y in data:
        if np.isnan(x) or np.isnan(y):
            coords_list.append(None)
        else:
            coords_list.append([float(x), float(y)])
    coordinates[short_name] = coords_list
```

> **TODO: Performance optimization**
> For better performance with large datasets (100k+ frames), consider binary transfer using `traitlets.Bytes()` and `Float32Array` views in JavaScript. This could reduce data size by ~5x and eliminate JSON parsing overhead. See anywidget patterns by Trevor Manz for reference implementation. The current JSON approach was chosen for simplicity and reliability.

### 2. State Synchronization with Traitlets

[Traitlets](https://traitlets.readthedocs.io/) is a Python library for defining typed attributes with validation, defaults, and change observation. Originally developed for IPython/Jupyter, it provides the foundation for widget state management.

**Key traitlets concepts:**

- **Typed attributes**: `traitlets.Unicode()`, `traitlets.Dict()`, `traitlets.List()`, `traitlets.Bool()` define the expected type and provide validation
- **Default values**: Each trait can have a default, e.g., `traitlets.Bool(True)`
- **Change observation**: You can observe changes with `@observe('trait_name')` decorators
- **Synchronization tag**: `.tag(sync=True)` marks traits that should sync between Python and JavaScript

```python
class NWBPoseEstimationWidget(anywidget.AnyWidget):
    # Keypoint metadata (colors, labels)
    keypoint_metadata = traitlets.Dict({}).tag(sync=True)

    # Pose data as JSON
    pose_coordinates = traitlets.Dict({}).tag(sync=True)  # {keypoint_name: [[x, y], ...]}
    timestamps = traitlets.List([]).tag(sync=True)
```

When a synced trait changes in Python, the change propagates to JavaScript (and vice versa) via Jupyter's comm protocol. This bidirectional sync is what makes interactive widgets possible.

### 3. Camera Selection

The widget supports multiple cameras (Left, Body, Right) when available. Not all sessions have all cameras, so the widget:
- Discovers available cameras from the pose estimation data
- Only shows cameras that have both video files and pose data
- Gracefully handles missing cameras by filtering them from the dropdown

```python
# User provides explicit mapping from pose camera names to video URL keys
camera_to_video_key = {
    'LeftCamera': 'VideoLeftCamera',
    'BodyCamera': 'VideoBodyCamera',
    'RightCamera': 'VideoRightCamera',
}
# Empty strings are filtered out - only cameras with URLs are shown
```

### 4. Video Streaming

The HTML5 `<video>` element streams directly from the S3 URL. The browser handles buffering and seeking natively - no data passes through Python.

### 5. Canvas Overlay

A transparent `<canvas>` element is positioned exactly over the video using CSS absolute positioning. Keypoints are drawn on this canvas, which updates independently of the video.

```javascript
const canvas = document.createElement('canvas');
canvas.style.position = 'absolute';
canvas.style.top = '0';
canvas.style.left = '0';
```

### 6. Multi-Video Synchronization

The multi-camera video widget (`NWBFileVideoPlayer`) displays multiple videos simultaneously. Since each HTML5 `<video>` element plays independently, videos can drift apart due to:
- Network latency differences (each video streams from a separate S3 URL)
- Buffering and decoding speed variations
- Browser scheduling differences

**Synchronization approach:**

The widget uses a master-slave pattern with continuous drift correction:

```javascript
function syncVideos() {
  if (videos.length < 2 || !isPlaying) return;

  const masterTime = videos[0].currentTime;
  for (let i = 1; i < videos.length; i++) {
    const drift = videos[i].currentTime - masterTime;
    // Correct if drift exceeds 100ms
    if (Math.abs(drift) > 0.1) {
      videos[i].currentTime = masterTime;
    }
  }

  syncAnimationId = requestAnimationFrame(syncVideos);
}
```

**How it works:**

1. **Master video**: The first video (`videos[0]`) is the timing reference
2. **Drift detection**: On each animation frame (~60fps), check each video's time against the master
3. **Correction threshold**: Only correct if drift exceeds 100ms to avoid constant seeking
4. **Continuous monitoring**: Uses `requestAnimationFrame` for efficient polling during playback

**Trade-offs:**

- The 100ms threshold balances smoothness vs. sync accuracy
- Correcting drift causes a brief seek, which may cause a visual "jump"
- If the master video buffers, other videos continue briefly before correction

**Alternative approaches not used:**

- **Media Source Extensions (MSE)**: Would allow frame-accurate sync but requires server-side segmentation
- **Web Audio API for timing**: More precise but adds complexity
- **Pausing all on buffer**: Would prevent drift but creates jerky playback

## Why It's Performant

### No Python in the Render Loop

Once the widget initializes, all rendering happens in JavaScript. Video frames and pose drawing never touch the Python kernel. This is critical - Python kernel round-trips would add hundreds of milliseconds of latency per frame.

### Native Video Streaming

The browser's media pipeline handles video decoding and S3 range requests. This is the same optimized code path used by YouTube, Netflix, etc. The browser:
- Makes HTTP range requests to fetch only needed video chunks
- Uses hardware video decoding when available
- Manages buffering automatically

### RequestAnimationFrame

During playback, pose updates use `requestAnimationFrame()` which:
- Syncs with the display refresh rate (typically 60Hz)
- Pauses automatically when the tab is hidden
- Batches DOM updates efficiently

```javascript
function animate() {
    drawPose();
    if (isPlaying) animationId = requestAnimationFrame(animate);
}
```

### Binary Search for Frame Lookup

Finding the correct pose frame for a given video timestamp uses O(log n) binary search rather than O(n) linear scan:

```javascript
function findFrameIndex(timestamps, targetTime) {
    let left = 0, right = timestamps.length - 1;
    while (left < right) {
        const mid = Math.floor((left + right) / 2);
        if (timestamps[mid] < targetTime) left = mid + 1;
        else right = mid;
    }
    return left;
}
```

### Minimal Data Transfer

Pose coordinates are sent once during widget creation (as JSON). Only visibility toggles and playback state cross the Python-JS boundary during interaction.

## Architecture

```
Python (runs once)              JavaScript (runs continuously)
-----------------              ----------------------------
keypoint_metadata  --JSON-->   model.get('keypoint_metadata')
pose_coordinates   --JSON-->   model.get('pose_coordinates')
timestamps         --JSON-->   model.get('timestamps')
video_url string   --sync-->   video.src = url

                               video element <-- S3 streaming
                               canvas.drawPose() <-- requestAnimationFrame
```

## Temporal Alignment

The video file starts at time 0, but NWB timestamps start at the session's first timestamp (e.g., 3.56s). The alignment is:

```javascript
// Video time 0 corresponds to timestamps[0]
const timestamps = model.get('timestamps');
const nwbTime = timestamps[0] + video.currentTime;
const frameIdx = findFrameIndex(timestamps, nwbTime);
```

## Spatial Alignment

Pose coordinates are in the native video resolution (e.g., 1280x1024). When displaying at a smaller size (e.g., 640x512), coordinates are scaled:

```javascript
const scaleX = displayWidth / video.videoWidth;
const scaleY = displayHeight / video.videoHeight;
const x = rawX * scaleX;
const y = rawY * scaleY;
```

The video element uses `object-fit: fill` to ensure the video fills the exact display dimensions without letterboxing, maintaining pixel-perfect alignment with the canvas overlay.

---

## Introduction to anywidget

[anywidget](https://anywidget.dev/) is a specification and framework for building portable Jupyter widgets. It solves a long-standing problem in the Jupyter ecosystem: creating interactive visualizations that work across all notebook environments.

### The Problem anywidget Solves

Traditional Jupyter widgets (ipywidgets) require:
1. A Python package with widget code
2. A JavaScript package (npm) with frontend code
3. Complex build tooling (webpack, etc.)
4. Installation of both packages in sync
5. Different setup for JupyterLab vs Jupyter Notebook vs VS Code

This complexity meant that most scientists either avoided custom widgets entirely or relied on pre-built libraries. Creating a simple interactive visualization required significant frontend engineering expertise.

### The anywidget Solution

anywidget lets you define the entire widget in a single Python file:

```python
import anywidget
import traitlets

class CounterWidget(anywidget.AnyWidget):
    count = traitlets.Int(0).tag(sync=True)

    _esm = """
    function render({ model, el }) {
        const button = document.createElement('button');
        button.textContent = 'Count: ' + model.get('count');
        button.onclick = () => {
            model.set('count', model.get('count') + 1);
            model.save_changes();
            button.textContent = 'Count: ' + model.get('count');
        };
        el.appendChild(button);
    }
    export default { render };
    """
```

**Key benefits:**
- **Single file**: Everything lives in one `.py` file
- **No build step**: JavaScript is embedded as a string (ESM format)
- **Universal**: Works in JupyterLab, Jupyter Notebook, VS Code, Google Colab, and more
- **Hot reload**: Changes take effect immediately during development

### How anywidget Works Internally

1. **Widget Registration**: When you create an anywidget class, it registers with Jupyter's widget system using the `@jupyter-widgets/base` protocol.

2. **ESM Loading**: The `_esm` string is sent to the browser and loaded as an ES Module. This avoids the need for bundling tools.

3. **Model-View Pattern**: anywidget follows the same Model-View architecture as ipywidgets:
   - **Model** (Python side): Holds the widget state (traitlets)
   - **View** (JavaScript side): Renders the UI and handles user interaction
   - **Comm**: Jupyter's communication channel syncs state bidirectionally

4. **Traitlets Bridge**: Properties marked with `.tag(sync=True)` are serialized to JSON (or sent as binary for `Bytes`) and sent over Jupyter's comm channel whenever they change.

### The `render` Function

The JavaScript side must export a `render` function that receives:
- `model`: A proxy to access synced traitlets via `model.get('name')` and `model.set('name', value)`
- `el`: The DOM element where the widget should render

```javascript
function render({ model, el }) {
    // Read state from Python
    const metadata = model.get('keypoint_metadata');

    // For binary data, create typed array views
    const coordsBuffer = model.get('pose_coordinates');
    const coordsView = new Float32Array(coordsBuffer.buffer);

    // Create DOM elements
    const canvas = document.createElement('canvas');
    el.appendChild(canvas);

    // Update state back to Python
    model.set('visible_keypoints', newVisibility);
    model.save_changes();  // Required to sync back

    // Listen for changes from Python
    model.on('change:pose_coordinates', () => {
        // Update views when binary data changes
    });
}
export default { render };
```

### Why ESM (ES Modules)?

anywidget uses ES Modules (the `export default` syntax) because:
- **Native browser support**: No transpilation needed
- **Dynamic imports**: Can load additional libraries on demand
- **Isolation**: Each widget gets its own module scope

You can even import external libraries:

```javascript
_esm = """
import * as d3 from 'https://esm.sh/d3@7.9.0';

function render({ model, el }) {
    d3.select(el).append('svg')...
}
export default { render };
"""
```

### Comparison with ipywidgets

| Feature | ipywidgets | anywidget |
|---------|-----------|-----------|
| Requires npm package | Yes | No |
| Requires build tools | Yes | No |
| Single-file widgets | No | Yes |
| Works in Colab | Sometimes | Yes |
| Hot reload | No | Yes |
| TypeScript support | Via build | Optional |
| Binary data support | Yes | Yes |

### When to Use anywidget

anywidget is ideal for:
- Quick prototypes and one-off visualizations
- Embedding interactive elements in notebooks
- Sharing reproducible widgets (just share the `.py` file)
- Scientists who know some JavaScript but not frontend tooling

For production widgets with complex UIs, team development, or when you need TypeScript, you might still want a traditional ipywidget with proper build tooling. But anywidget has made the "hello world" to "useful widget" path dramatically shorter.

---

## Future Style Improvements

The current widgets are functional but use basic browser styling. Here are improvements to consider for a more polished look, based on modern CSS best practices.

### CSS Architecture

**Scoped Class Names**: Since anywidget loads CSS in global scope, prefix all classes to avoid conflicts:

```css
.pose-widget { /* wrapper */ }
.pose-widget__button { /* BEM naming */ }
.pose-widget__controls { }
```

**File-Based CSS**: Separating CSS enables Hot Module Replacement (HMR) during development:

```python
class NWBPoseEstimationWidget(anywidget.AnyWidget):
    _esm = pathlib.Path(__file__).parent / "nwb_pose_widget.js"
    _css = pathlib.Path(__file__).parent / "nwb_pose_widget.css"
```

### Modern Button Styling

Apply proper reset styles and use flexbox for alignment. The 44px minimum height meets [WCAG 2.1 touch target requirements](https://www.w3.org/WAI/WCAG21/Understanding/target-size.html):

```css
.pose-widget__button {
  /* Reset browser defaults */
  border: none;
  background-color: transparent;
  font-family: inherit;
  cursor: pointer;

  /* Flexbox for icon + text alignment */
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;

  /* Visual styling */
  background-color: #4a5568;
  color: #fff;
  border-radius: 8px;
  padding: 0.5em 1em;
  min-height: 44px;
  font-size: 14px;

  /* Layered shadows for realistic depth */
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.07),
    0 2px 4px rgba(0, 0, 0, 0.07),
    0 4px 8px rgba(0, 0, 0, 0.07);

  transition: all 180ms ease-out;
}

.pose-widget__button:hover {
  background-color: #2d3748;
  transform: translateY(-1px);
  box-shadow:
    0 2px 4px rgba(0, 0, 0, 0.1),
    0 4px 8px rgba(0, 0, 0, 0.1),
    0 8px 16px rgba(0, 0, 0, 0.1);
}

.pose-widget__button:active {
  transform: translateY(0);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

/* Accessible focus state - never remove outline without replacement */
.pose-widget__button:focus {
  outline: none;
  box-shadow:
    0 0 0 3px rgba(66, 153, 225, 0.5),
    0 1px 2px rgba(0, 0, 0, 0.07);
}
```

**Why layered shadows?** As [Josh Comeau explains](https://www.joshwcomeau.com/css/designing-shadows/), stacking multiple shadows with different offsets creates more realistic depth than a single shadow. Real-world shadows have complex falloff that a single `box-shadow` cannot replicate.

### Play/Pause Button with Icons

Use inline SVG for crisp icons at any size. SVG scales perfectly and can inherit `currentColor`:

```javascript
// In JavaScript - create SVG elements
function createIcon(type) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "currentColor");

  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  if (type === "play") {
    path.setAttribute("d", "M8 5v14l11-7z");  // Play triangle
  } else {
    path.setAttribute("d", "M6 19h4V5H6v14zm8-14v14h4V5h-4z");  // Pause bars
  }
  svg.appendChild(path);
  return svg;
}
```

Alternative: Unicode symbols (simpler but less consistent across platforms):
- Play: `\u25B6` or `&#9654;`
- Pause: `\u23F8` or `&#9208;`

### Custom Seek Bar (Cross-Browser)

Style the range input consistently across browsers:

```css
.pose-widget__seekbar {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  cursor: pointer;
}

/* Thumb - WebKit (Chrome, Safari, Edge) */
.pose-widget__seekbar::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #4a5568;
  border: 2px solid #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  cursor: grab;
  transition: transform 150ms ease;
}

.pose-widget__seekbar::-webkit-slider-thumb:hover {
  transform: scale(1.15);
}

.pose-widget__seekbar::-webkit-slider-thumb:active {
  cursor: grabbing;
  transform: scale(1.1);
}

/* Thumb - Firefox */
.pose-widget__seekbar::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #4a5568;
  border: 2px solid #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  cursor: grab;
}

/* Track - Firefox */
.pose-widget__seekbar::-moz-range-track {
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
}

/* Focus state */
.pose-widget__seekbar:focus {
  outline: none;
}
.pose-widget__seekbar:focus::-webkit-slider-thumb {
  box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.5);
}
```

### Video Container

Add subtle borders and rounded corners. The `overflow: hidden` ensures the canvas overlay respects the border radius:

```css
.pose-widget__video-container {
  position: relative;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  overflow: hidden;
  background: #1a1a1a;  /* Dark fallback while loading */
}

.pose-widget__video {
  display: block;
  width: 100%;
  height: auto;
  object-fit: fill;
}

.pose-widget__canvas {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
}
```

### Keypoint Toggle Buttons

Pill-shaped toggles with clear active states. The `box-shadow` ring indicates selection without layout shift:

```css
.pose-widget__keypoint-toggle {
  border: none;
  border-radius: 16px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 150ms ease;

  /* Inactive state */
  background: #f5f5f5;
  color: #718096;
}

.pose-widget__keypoint-toggle:hover {
  background: #e2e8f0;
}

.pose-widget__keypoint-toggle--active {
  color: #fff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
  /* Background color set dynamically from keypoint color */
}

/* Focus ring for keyboard navigation */
.pose-widget__keypoint-toggle:focus {
  outline: none;
  box-shadow: 0 0 0 2px #fff, 0 0 0 4px currentColor;
}

/* Utility buttons (All/None) */
.pose-widget__keypoint-toggle--utility {
  background: #e2e8f0;
  color: #4a5568;
  border: 1px solid #cbd5e0;
}
```

### Debug Info Panel

Subtle styling that does not distract from the video:

```css
.pose-widget__debug {
  font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 11px;
  color: #718096;
  background: transparent;
  border-left: 2px solid #e2e8f0;
  padding: 4px 0 4px 12px;
  margin: 8px 0;
  line-height: 1.4;
}

/* Optional: hide by default, show on hover */
.pose-widget__debug--collapsible {
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  transition: all 200ms ease;
}

.pose-widget:hover .pose-widget__debug--collapsible {
  max-height: 50px;
  opacity: 1;
}
```

### Camera Selector Dropdown

Style the select element to match the overall design:

```css
.pose-widget__select {
  appearance: none;
  -webkit-appearance: none;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 8px 32px 8px 12px;
  background-color: #fff;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%234a5568' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  font-size: 14px;
  cursor: pointer;
  min-width: 150px;
}

.pose-widget__select:hover {
  border-color: #cbd5e0;
}

.pose-widget__select:focus {
  outline: none;
  border-color: #4299e1;
  box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.25);
}
```

### Loading State

Show visual feedback while video buffers:

```css
/* Loading spinner overlay */
.pose-widget__loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: none;
}

.pose-widget__video-container--loading .pose-widget__loading {
  display: block;
}

.pose-widget__spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #e2e8f0;
  border-top-color: #4299e1;
  border-radius: 50%;
  animation: pose-widget-spin 0.8s linear infinite;
}

@keyframes pose-widget-spin {
  to { transform: rotate(360deg); }
}
```

In JavaScript, toggle the loading class:

```javascript
video.addEventListener("loadstart", () => {
  videoContainer.classList.add("pose-widget__video-container--loading");
});
video.addEventListener("canplay", () => {
  videoContainer.classList.remove("pose-widget__video-container--loading");
});
```

### Color Palette

A cohesive neutral palette inspired by Tailwind CSS:

| Purpose | Color | Usage |
|---------|-------|-------|
| Background | `#f7fafc` | Widget wrapper |
| Surface | `#ffffff` | Controls, dropdowns |
| Border | `#e2e8f0` | Dividers, input borders |
| Border hover | `#cbd5e0` | Interactive elements |
| Text primary | `#2d3748` | Main labels |
| Text secondary | `#718096` | Debug info, hints |
| Accent | `#4299e1` | Focus rings, active states |
| Accent dark | `#3182ce` | Accent hover |
| Dark surface | `#4a5568` | Buttons |
| Dark hover | `#2d3748` | Button hover |

### Layout and Spacing

Use CSS custom properties for consistent spacing:

```css
.pose-widget {
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 12px;
  --spacing-lg: 16px;
  --spacing-xl: 24px;

  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  padding: var(--spacing-lg);
  background: #f7fafc;
  border-radius: 12px;
}

.pose-widget__section {
  margin-bottom: var(--spacing-md);
}

.pose-widget__controls {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm);
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
```

### Accessibility Checklist

Based on [Modern CSS Button Guide](https://moderncss.dev/css-button-styling-guide/) recommendations:

- **Touch targets**: Minimum 44x44px for buttons (WCAG 2.1)
- **Color contrast**: 4.5:1 for text, 3:1 for UI components
- **Focus indicators**: Never remove without replacement; use `box-shadow` to avoid layout shift
- **Keyboard navigation**: All interactive elements focusable and operable
- **High contrast mode**: Add fallback borders for Windows High Contrast

```css
@media (forced-colors: active) {
  .pose-widget__button {
    border: 2px solid currentColor;
  }
}
```

### Implementation Notes

1. **Add class to wrapper**: In `render()`, add `el.classList.add("pose-widget")` to enable scoped styles

2. **Replace inline styles**: Convert `element.style.property = value` to CSS classes

3. **Maintain keypoint colors**: Dynamic colors (from Python) should still be applied inline for the keypoint-specific toggles

4. **Test across environments**: Verify styling in JupyterLab, VS Code notebooks, and Google Colab

### References

- [Designing Beautiful Shadows in CSS](https://www.joshwcomeau.com/css/designing-shadows/) - Layered shadow techniques
- [CSS Button Styling Guide](https://moderncss.dev/css-button-styling-guide/) - Accessibility and reset patterns
- [anywidget Documentation](https://anywidget.dev/en/getting-started/) - CSS attribute and HMR
- [MDN: Styling Video Controls](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Audio_and_video_delivery/Video_player_styling_basics) - Custom media player styling

---

## Packaging Widgets as Standalone PyPI Packages

If you want to distribute an anywidget as its own reusable package (separate from this project), this section covers the process from project setup to PyPI publishing.

### Why Package Separately?

- **Reusability**: Others can `pip install` your widget without the full IBL-to-NWB project
- **Versioning**: Independent release cycle for the widget
- **Smaller footprint**: Users only install what they need
- **Discoverability**: Listed on PyPI and searchable

### Project Structure

A minimal standalone anywidget package looks like this:

```
my-widget/
├── pyproject.toml           # Build configuration and metadata
├── README.md                 # Package description for PyPI
├── LICENSE                   # License file
└── src/
    └── my_widget/
        ├── __init__.py       # Re-export widget class
        ├── widget.py         # Python widget class
        ├── widget.js         # JavaScript frontend code
        └── widget.css        # CSS styles (optional)
```

The `src/` layout is recommended by Python packaging best practices to avoid import confusion.

### pyproject.toml Configuration

Here is a complete `pyproject.toml` for an anywidget package using hatchling as the build backend:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "my-widget"
version = "0.1.0"
description = "A reusable Jupyter widget for..."
readme = "README.md"
license = "MIT"
authors = [
    { name = "Your Name", email = "you@example.com" }
]
keywords = ["jupyter", "widget", "anywidget", "visualization"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Framework :: Jupyter",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
requires-python = ">=3.10"
dependencies = [
    "anywidget>=0.9.0",
    # Add other runtime dependencies here
]

[project.optional-dependencies]
dev = [
    "pytest",
    "ruff",
]

[project.urls]
Homepage = "https://github.com/yourname/my-widget"
Repository = "https://github.com/yourname/my-widget"

[tool.hatch.build]
# Include static files (JS, CSS) in the built package
artifacts = ["src/my_widget/*.js", "src/my_widget/*.css"]
```

**Key points:**

- **artifacts**: Hatchling by default only includes `.py` files. The `artifacts` setting ensures your `.js` and `.css` files are included in the wheel.
- **anywidget dependency**: Specify `>=0.9.0` or whatever version introduced features you use.

### Widget Implementation

**widget.py**:

```python
"""My reusable Jupyter widget."""
import pathlib
import anywidget
import traitlets

class MyWidget(anywidget.AnyWidget):
    """A widget that does something useful."""

    # Synced traitlets
    data = traitlets.Dict({}).tag(sync=True)
    selected = traitlets.Unicode("").tag(sync=True)

    # File paths relative to this Python file
    _esm = pathlib.Path(__file__).parent / "widget.js"
    _css = pathlib.Path(__file__).parent / "widget.css"

    def __init__(self, data=None, **kwargs):
        super().__init__(data=data or {}, **kwargs)
```

**Important**: Use `pathlib.Path(__file__).parent` to reference sibling files. This works regardless of where the package is installed.

**__init__.py**:

```python
"""My widget package."""
from .widget import MyWidget

__all__ = ["MyWidget"]
__version__ = "0.1.0"
```

### Scaffolding with create-anywidget

For a quicker start, use the `create-anywidget` npm scaffolding tool:

```bash
npm create anywidget@latest
```

This interactive tool prompts you for:
- Package name
- Template type (vanilla JS, React, etc.)
- Python package manager preference

It generates:
- A complete project structure
- Pre-configured `pyproject.toml`
- Example widget code
- Development scripts

### Development Workflow

1. **Install in editable mode**:
   ```bash
   pip install -e ".[dev]"
   ```

2. **Test in a notebook**: Create a test notebook and import your widget. With anywidget's hot module replacement (HMR), changes to `.js` and `.css` files appear immediately without kernel restart.

3. **Run linting**:
   ```bash
   ruff check src/
   ```

### Building the Package

Build a source distribution and wheel:

```bash
pip install build
python -m build
```

This creates:
- `dist/my_widget-0.1.0.tar.gz` (source distribution)
- `dist/my_widget-0.1.0-py3-none-any.whl` (wheel)

Verify the wheel contains your static files:

```bash
unzip -l dist/my_widget-0.1.0-py3-none-any.whl
```

You should see `my_widget/widget.js` and `my_widget/widget.css` listed.

### Publishing to PyPI

1. **Create a PyPI account** at https://pypi.org/account/register/

2. **Create an API token** at https://pypi.org/manage/account/token/

3. **Install twine**:
   ```bash
   pip install twine
   ```

4. **Upload** (first test on TestPyPI):
   ```bash
   # Test upload
   twine upload --repository testpypi dist/*

   # Production upload
   twine upload dist/*
   ```

5. **Verify installation**:
   ```bash
   pip install my-widget
   ```

### Automating with GitHub Actions

Create `.github/workflows/publish.yml` for automatic publishing on release:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install build tools
        run: pip install build twine

      - name: Build package
        run: python -m build

      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
        run: twine upload dist/*
```

Add your PyPI API token as a repository secret named `PYPI_API_TOKEN`.

### Example Packages

These anywidget packages on PyPI can serve as references:

- **[wigglystuff](https://github.com/koaning/wigglystuff)**: Simple widgets demonstrating the pattern
- **[drawdata](https://github.com/koaning/drawdata)**: Interactive data drawing widget
- **[lonboard](https://github.com/developmentseed/lonboard)**: Large-scale geospatial visualization

### Checklist Before Publishing

- [ ] Version bumped in `pyproject.toml` and `__init__.py`
- [ ] README has clear installation and usage instructions
- [ ] LICENSE file present
- [ ] Tested `pip install` from built wheel
- [ ] Static files (JS, CSS) included in wheel
- [ ] Works in JupyterLab, VS Code notebooks, and Colab
- [ ] All dependencies listed in `pyproject.toml`

### References

- [anywidget Getting Started](https://anywidget.dev/en/getting-started/) - Official documentation
- [create-anywidget](https://github.com/manzt/anywidget/tree/main/packages/create-anywidget) - Project scaffolding tool
- [Python Packaging User Guide](https://packaging.python.org/) - Official packaging documentation
- [hatchling documentation](https://hatch.pypa.io/latest/) - Build backend configuration
