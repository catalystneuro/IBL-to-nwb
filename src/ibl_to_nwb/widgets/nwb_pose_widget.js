/**
 * Pose estimation video player widget.
 * Overlays DeepLabCut keypoints on streaming video with camera selection.
 *
 * Binary data format (from Python):
 * - pose_coordinates: Float32Array of shape [n_keypoints, n_frames, 2]
 *   Stored as little-endian bytes, accessed via Float32Array view
 * - timestamps_binary: Float64Array of shape [n_frames]
 *   Stored as little-endian bytes, accessed via Float64Array view
 *
 * Why binary? See Python code comments - 5x smaller than JSON, instant parsing.
 */

const DISPLAY_WIDTH = 640;
const DISPLAY_HEIGHT = 512;

/**
 * Binary search for frame index closest to target time.
 * @param {Float64Array} timestamps - Sorted array of timestamps
 * @param {number} targetTime - Time to find
 * @returns {number} Index of closest timestamp
 */
function findFrameIndex(timestamps, targetTime) {
  if (!timestamps || timestamps.length === 0) return 0;
  let left = 0;
  let right = timestamps.length - 1;
  while (left < right) {
    const mid = Math.floor((left + right) / 2);
    if (timestamps[mid] < targetTime) {
      left = mid + 1;
    } else {
      right = mid;
    }
  }
  return left;
}

/**
 * Render the pose video player widget.
 *
 * This is the entry point called by anywidget when the widget is displayed.
 *
 * @param {Object} context - Provided by anywidget
 * @param {Object} context.model - Proxy to Python traitlets. Use model.get('name')
 *   to read synced traits and model.set('name', value) + model.save_changes()
 *   to update them. Listen for changes with model.on('change:name', callback).
 * @param {HTMLElement} context.el - The DOM element where the widget should render.
 *   Append all UI elements to this container.
 */
function render({ model, el }) {
  const wrapper = document.createElement("div");
  wrapper.style.fontFamily = "sans-serif";

  // Camera selector
  const cameraSelector = document.createElement("div");
  cameraSelector.style.marginBottom = "10px";
  cameraSelector.style.display = "flex";
  cameraSelector.style.alignItems = "center";
  cameraSelector.style.gap = "10px";

  const cameraLabel = document.createElement("span");
  cameraLabel.textContent = "Camera:";
  cameraLabel.style.fontWeight = "bold";

  const cameraSelect = document.createElement("select");
  cameraSelect.style.padding = "5px 10px";
  cameraSelect.style.fontSize = "14px";

  cameraSelector.appendChild(cameraLabel);
  cameraSelector.appendChild(cameraSelect);

  // Debug info
  const debugDiv = document.createElement("div");
  debugDiv.style.backgroundColor = "#f0f0f0";
  debugDiv.style.padding = "5px";
  debugDiv.style.marginBottom = "10px";
  debugDiv.style.fontSize = "12px";
  debugDiv.style.fontFamily = "monospace";

  // Keypoint toggles
  const keypointToggles = document.createElement("div");
  keypointToggles.style.marginBottom = "10px";
  keypointToggles.style.display = "flex";
  keypointToggles.style.flexWrap = "wrap";
  keypointToggles.style.gap = "5px";

  // Controls
  const controls = document.createElement("div");
  controls.style.marginBottom = "10px";
  controls.style.display = "flex";
  controls.style.alignItems = "center";
  controls.style.gap = "10px";

  const playPauseBtn = document.createElement("button");
  playPauseBtn.textContent = "Play";
  playPauseBtn.style.padding = "8px 16px";
  playPauseBtn.style.cursor = "pointer";

  const seekBar = document.createElement("input");
  seekBar.type = "range";
  seekBar.min = 0;
  seekBar.max = 100;
  seekBar.value = 0;
  seekBar.style.flex = "1";

  const labelToggle = document.createElement("label");
  labelToggle.style.display = "flex";
  labelToggle.style.alignItems = "center";
  labelToggle.style.gap = "4px";
  labelToggle.style.cursor = "pointer";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = model.get("show_labels");
  labelToggle.appendChild(checkbox);
  labelToggle.appendChild(document.createTextNode("Labels"));

  controls.appendChild(playPauseBtn);
  controls.appendChild(seekBar);
  controls.appendChild(labelToggle);

  // Video container
  const videoContainer = document.createElement("div");
  videoContainer.style.position = "relative";
  videoContainer.style.width = DISPLAY_WIDTH + "px";
  videoContainer.style.height = DISPLAY_HEIGHT + "px";

  const video = document.createElement("video");
  video.style.width = DISPLAY_WIDTH + "px";
  video.style.height = DISPLAY_HEIGHT + "px";
  video.style.objectFit = "fill";
  video.style.display = "block";
  video.style.backgroundColor = "#000";
  video.muted = true;
  video.playsInline = true;

  const canvas = document.createElement("canvas");
  canvas.width = DISPLAY_WIDTH;
  canvas.height = DISPLAY_HEIGHT;
  canvas.style.position = "absolute";
  canvas.style.top = "0";
  canvas.style.left = "0";
  canvas.style.pointerEvents = "none";

  videoContainer.appendChild(video);
  videoContainer.appendChild(canvas);

  let isPlaying = false;
  let animationId = null;
  let visibleKeypoints = { ...model.get("visible_keypoints") };

  // Typed array views for binary data - these are recreated when data changes
  // Using views avoids copying data - just interprets the underlying ArrayBuffer
  let coordsView = null; // Float32Array view of pose_coordinates
  let timestampsView = null; // Float64Array view of timestamps_binary
  let nFrames = 0;
  let nKeypoints = 0;
  let keypointOrder = [];

  /**
   * Update typed array views when binary data changes.
   * Creates Float32Array/Float64Array views over the raw bytes.
   *
   * anywidget sends Bytes traitlets as DataView objects. We create typed
   * array views using the DataView's byteOffset and byteLength to get the
   * correct slice of the underlying shared buffer.
   */
  function updateDataViews() {
    const coordsBuffer = model.get("pose_coordinates");
    const timestampsBuffer = model.get("timestamps_binary");
    nFrames = model.get("n_frames");
    nKeypoints = model.get("n_keypoints");
    keypointOrder = model.get("keypoint_order");

    if (coordsBuffer && coordsBuffer.byteLength > 0) {
      // Create Float32Array view with correct offset and length from DataView
      coordsView = new Float32Array(
        coordsBuffer.buffer,
        coordsBuffer.byteOffset,
        coordsBuffer.byteLength / 4
      );
    } else {
      coordsView = null;
    }

    if (timestampsBuffer && timestampsBuffer.byteLength > 0) {
      // Create Float64Array view with correct offset and length from DataView
      timestampsView = new Float64Array(
        timestampsBuffer.buffer,
        timestampsBuffer.byteOffset,
        timestampsBuffer.byteLength / 8
      );
    } else {
      timestampsView = null;
    }

    seekBar.max = nFrames > 0 ? nFrames - 1 : 100;
  }

  /**
   * Get coordinate for a keypoint at a frame.
   * @param {number} keypointIdx - Index in keypoint_order
   * @param {number} frameIdx - Frame index
   * @returns {{x: number, y: number} | null} Coordinates or null if NaN
   */
  function getCoord(keypointIdx, frameIdx) {
    if (!coordsView) return null;

    // Data layout: [n_keypoints][n_frames][2]
    // Index calculation: (keypointIdx * n_frames * 2) + (frameIdx * 2) + (0 or 1)
    const baseIdx = keypointIdx * nFrames * 2 + frameIdx * 2;
    const x = coordsView[baseIdx];
    const y = coordsView[baseIdx + 1];

    // NaN check - IEEE 754 NaN values come through as NaN in Float32Array
    if (Number.isNaN(x) || Number.isNaN(y)) return null;

    return { x, y };
  }

  /**
   * Update debug info display.
   * @param {number} frameIdx - Current frame index
   * @param {string} [extra] - Additional status text
   */
  function updateDebug(frameIdx, extra = "") {
    const camera = model.get("selected_camera");
    const coordsInfo = coordsView
      ? `coords[${coordsView.length}]`
      : "coords=null";
    debugDiv.textContent =
      camera +
      " | Frame: " +
      frameIdx +
      "/" +
      nFrames +
      " | Video: " +
      video.videoWidth +
      "x" +
      video.videoHeight +
      " | " +
      coordsInfo +
      " | " +
      extra;
  }

  function populateCameraSelect() {
    cameraSelect.innerHTML = "";
    const cameras = model.get("available_cameras");
    const selected = model.get("selected_camera");
    cameras.forEach((cam) => {
      const opt = document.createElement("option");
      opt.value = cam;
      opt.textContent = cam;
      if (cam === selected) opt.selected = true;
      cameraSelect.appendChild(opt);
    });
  }

  function updateToggleStyles() {
    const buttons = keypointToggles.querySelectorAll("button[data-keypoint]");
    const metadata = model.get("keypoint_metadata");
    buttons.forEach((btn) => {
      const name = btn.dataset.keypoint;
      const isVisible = visibleKeypoints[name] !== false;
      const color = metadata[name]?.color || "#999";
      btn.style.backgroundColor = isVisible ? color : "#f5f5f5";
      btn.style.color = isVisible ? "#fff" : "#999";
      btn.style.textShadow = isVisible ? "0 0 2px #000" : "none";
    });
  }

  function createKeypointToggles() {
    keypointToggles.innerHTML = "";
    const metadata = model.get("keypoint_metadata");
    if (!metadata || Object.keys(metadata).length === 0) return;

    const allBtn = document.createElement("button");
    allBtn.textContent = "All";
    allBtn.style.padding = "4px 8px";
    allBtn.style.fontSize = "11px";
    allBtn.style.cursor = "pointer";
    allBtn.style.backgroundColor = "#ddd";
    allBtn.style.border = "1px solid #999";
    allBtn.style.borderRadius = "3px";
    allBtn.addEventListener("click", () => {
      for (const name of Object.keys(metadata)) visibleKeypoints[name] = true;
      model.set("visible_keypoints", { ...visibleKeypoints });
      model.save_changes();
      updateToggleStyles();
      drawPose();
    });

    const noneBtn = document.createElement("button");
    noneBtn.textContent = "None";
    noneBtn.style.padding = "4px 8px";
    noneBtn.style.fontSize = "11px";
    noneBtn.style.cursor = "pointer";
    noneBtn.style.backgroundColor = "#ddd";
    noneBtn.style.border = "1px solid #999";
    noneBtn.style.borderRadius = "3px";
    noneBtn.addEventListener("click", () => {
      for (const name of Object.keys(metadata)) visibleKeypoints[name] = false;
      model.set("visible_keypoints", { ...visibleKeypoints });
      model.save_changes();
      updateToggleStyles();
      drawPose();
    });

    keypointToggles.appendChild(allBtn);
    keypointToggles.appendChild(noneBtn);

    const sep = document.createElement("span");
    sep.style.borderLeft = "1px solid #ccc";
    sep.style.margin = "0 5px";
    sep.style.height = "20px";
    keypointToggles.appendChild(sep);

    for (const [name, kp] of Object.entries(metadata)) {
      const btn = document.createElement("button");
      btn.textContent = name;
      btn.dataset.keypoint = name;
      btn.style.padding = "4px 8px";
      btn.style.fontSize = "11px";
      btn.style.cursor = "pointer";
      btn.style.borderRadius = "3px";
      btn.style.border = "2px solid " + kp.color;
      btn.addEventListener("click", () => {
        visibleKeypoints[name] = !visibleKeypoints[name];
        model.set("visible_keypoints", { ...visibleKeypoints });
        model.save_changes();
        updateToggleStyles();
        drawPose();
      });
      keypointToggles.appendChild(btn);
    }
    updateToggleStyles();
  }

  /**
   * Get current frame index based on video time.
   * @returns {number}
   */
  function getFrameIndex() {
    if (!timestampsView || timestampsView.length === 0) return 0;
    return findFrameIndex(timestampsView, timestampsView[0] + video.currentTime);
  }

  /**
   * Draw pose keypoints on canvas overlay.
   */
  function drawPose() {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const metadata = model.get("keypoint_metadata");
    const showLabels = model.get("show_labels");

    if (!coordsView || nKeypoints === 0) {
      updateDebug(0, "No pose data");
      return;
    }

    const frameIdx = getFrameIndex();

    if (!video.videoWidth || !video.videoHeight) {
      updateDebug(frameIdx, "Loading video...");
      return;
    }

    const scaleX = DISPLAY_WIDTH / video.videoWidth;
    const scaleY = DISPLAY_HEIGHT / video.videoHeight;

    let drawnCount = 0;

    // Iterate keypoints using order and index for binary data access
    for (let kpIdx = 0; kpIdx < keypointOrder.length; kpIdx++) {
      const name = keypointOrder[kpIdx];
      if (visibleKeypoints[name] === false) continue;

      const coord = getCoord(kpIdx, frameIdx);
      if (!coord) continue; // NaN or out of bounds

      const x = coord.x * scaleX;
      const y = coord.y * scaleY;
      const kp = metadata[name];

      ctx.beginPath();
      ctx.arc(x, y, 5, 0, 2 * Math.PI);
      ctx.fillStyle = kp?.color || "#fff";
      ctx.fill();
      ctx.strokeStyle = "#000";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      drawnCount++;

      if (showLabels && kp) {
        ctx.font = "bold 10px sans-serif";
        ctx.fillStyle = "#fff";
        ctx.strokeStyle = "#000";
        ctx.lineWidth = 2;
        ctx.strokeText(kp.label, x + 6, y + 3);
        ctx.fillText(kp.label, x + 6, y + 3);
      }
    }
    updateDebug(frameIdx, "Drew " + drawnCount + " keypoints");
  }

  function animate() {
    drawPose();
    if (isPlaying) animationId = requestAnimationFrame(animate);
  }

  function loadVideo() {
    const camera = model.get("selected_camera");
    const videoUrl = model.get("camera_to_video")[camera];
    if (videoUrl && video.src !== videoUrl) {
      video.src = videoUrl;
    }
  }

  // Initialize
  populateCameraSelect();
  updateDataViews();
  loadVideo();

  video.addEventListener("loadedmetadata", () => {
    drawPose();
  });

  video.addEventListener("seeked", drawPose);
  video.addEventListener("timeupdate", drawPose);

  // Watch for pose data changes (when camera switches, Python sends new binary data)
  model.on("change:pose_coordinates", () => {
    updateDataViews();
    visibleKeypoints = { ...model.get("visible_keypoints") };
    createKeypointToggles();
    drawPose();
  });

  model.on("change:keypoint_metadata", () => {
    createKeypointToggles();
  });

  cameraSelect.addEventListener("change", () => {
    if (isPlaying) {
      video.pause();
      playPauseBtn.textContent = "Play";
      if (animationId) cancelAnimationFrame(animationId);
      isPlaying = false;
    }
    debugDiv.textContent = "Loading camera data...";
    model.set("selected_camera", cameraSelect.value);
    model.save_changes();
    loadVideo();
  });

  playPauseBtn.addEventListener("click", () => {
    if (isPlaying) {
      video.pause();
      playPauseBtn.textContent = "Play";
      if (animationId) cancelAnimationFrame(animationId);
    } else {
      video.play();
      playPauseBtn.textContent = "Pause";
      animate();
    }
    isPlaying = !isPlaying;
  });

  seekBar.addEventListener("input", () => {
    const frameIdx = parseInt(seekBar.value);
    if (timestampsView && timestampsView.length > 0) {
      video.currentTime = timestampsView[frameIdx] - timestampsView[0];
    }
  });

  checkbox.addEventListener("change", () => {
    model.set("show_labels", checkbox.checked);
    model.save_changes();
    drawPose();
  });

  updateDebug(0, "Initializing...");

  // Initial UI setup
  createKeypointToggles();

  wrapper.appendChild(cameraSelector);
  wrapper.appendChild(debugDiv);
  wrapper.appendChild(keypointToggles);
  wrapper.appendChild(controls);
  wrapper.appendChild(videoContainer);
  el.appendChild(wrapper);

  // Cleanup function (called when widget is destroyed)
  return () => {
    if (animationId) {
      cancelAnimationFrame(animationId);
    }
  };
}

export default { render };
