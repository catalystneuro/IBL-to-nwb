# Pose Video Widget

The pose estimation widget overlays DeepLabCut keypoints directly on streaming video. This is implemented using [anywidget](https://anywidget.dev/), a framework for building Jupyter widgets that work across JupyterLab, Jupyter Notebook, VS Code, and Google Colab.

## How the Widget Works

### 1. Data Preparation (Python side)

Pose estimation coordinates and timestamps are extracted from the NWB file and converted to JSON-serializable lists. NaN values (missing detections) are replaced with `null` since JSON doesn't support NaN.

```python
pose_data[short_name] = {
    'x': [None if np.isnan(v) else float(v) for v in x_vals],
    'y': [None if np.isnan(v) else float(v) for v in y_vals],
    'color': '#FF0000',
    'label': short_name
}
```

### 2. State Synchronization with Traitlets

[Traitlets](https://traitlets.readthedocs.io/) is a Python library for defining typed attributes with validation, defaults, and change observation. Originally developed for IPython/Jupyter, it provides the foundation for widget state management.

**Key traitlets concepts:**

- **Typed attributes**: `traitlets.Unicode()`, `traitlets.Dict()`, `traitlets.List()`, `traitlets.Bool()` define the expected type and provide validation
- **Default values**: Each trait can have a default, e.g., `traitlets.Bool(True)`
- **Change observation**: You can observe changes with `@observe('trait_name')` decorators
- **Synchronization tag**: `.tag(sync=True)` marks traits that should sync between Python and JavaScript

```python
class PoseVideoPlayer(anywidget.AnyWidget):
    # These traits are synced to JavaScript
    video_url = traitlets.Unicode("").tag(sync=True)
    pose_data = traitlets.Dict({}).tag(sync=True)
    timestamps = traitlets.List([]).tag(sync=True)
    show_labels = traitlets.Bool(True).tag(sync=True)
```

When a synced trait changes in Python, the change propagates to JavaScript (and vice versa) via Jupyter's comm protocol. This bidirectional sync is what makes interactive widgets possible.

### 3. Camera Selection

The widget supports multiple cameras (Left, Body, Right) when available. Not all sessions have all cameras, so the widget:
- Discovers available cameras from the pose estimation data
- Only shows cameras that have both video files and pose data
- Gracefully handles missing cameras by filtering them from the dropdown

```python
camera_to_video = {
    'LeftCamera': video_s3_urls.get('VideoLeftCamera', ''),
    'BodyCamera': video_s3_urls.get('VideoBodyCamera', ''),
    'RightCamera': video_s3_urls.get('VideoRightCamera', ''),
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
function findFrameIndex(nwbTime) {
    let left = 0, right = timestamps.length - 1;
    while (left < right) {
        const mid = Math.floor((left + right) / 2);
        if (timestamps[mid] < nwbTime) left = mid + 1;
        else right = mid;
    }
    return left;
}
```

### Minimal Data Transfer

Pose coordinates are sent once during widget creation. Only visibility toggles and playback state cross the Python-JS boundary during interaction.

## Architecture

```
Python (runs once)              JavaScript (runs continuously)
-----------------              ----------------------------
pose_data dict    --sync-->    model.get('pose_data')
timestamps list   --sync-->    model.get('timestamps')
video_url string  --sync-->    video.src = url

                               video element <-- S3 streaming
                               canvas.drawPose() <-- requestAnimationFrame
```

## Temporal Alignment

The video file starts at time 0, but NWB timestamps start at the session's first timestamp (e.g., 3.56s). The alignment is:

```javascript
// Video time 0 corresponds to NWB timestamps[0]
const nwbTime = timestamps[0] + video.currentTime;
const frameIdx = findFrameIndex(nwbTime);
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

4. **Traitlets Bridge**: Properties marked with `.tag(sync=True)` are serialized to JSON and sent over Jupyter's comm channel whenever they change.

### The `render` Function

The JavaScript side must export a `render` function that receives:
- `model`: A proxy to access synced traitlets via `model.get('name')` and `model.set('name', value)`
- `el`: The DOM element where the widget should render

```javascript
function render({ model, el }) {
    // Read state from Python
    const data = model.get('pose_data');

    // Create DOM elements
    const canvas = document.createElement('canvas');
    el.appendChild(canvas);

    // Update state back to Python
    model.set('visible_keypoints', newVisibility);
    model.save_changes();  // Required to sync back

    // Listen for changes from Python
    model.on('change:pose_data', () => {
        redraw();
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
import * as d3 from 'https://esm.sh/d3@7';

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

### When to Use anywidget

anywidget is ideal for:
- Quick prototypes and one-off visualizations
- Embedding interactive elements in notebooks
- Sharing reproducible widgets (just share the `.py` file)
- Scientists who know some JavaScript but not frontend tooling

For production widgets with complex UIs, team development, or when you need TypeScript, you might still want a traditional ipywidget with proper build tooling. But anywidget has made the "hello world" to "useful widget" path dramatically shorter.

### Further Reading

- [anywidget documentation](https://anywidget.dev/)
- [anywidget GitHub](https://github.com/manzt/anywidget)
- [Traitlets documentation](https://traitlets.readthedocs.io/)
- [Jupyter Widgets documentation](https://ipywidgets.readthedocs.io/)
