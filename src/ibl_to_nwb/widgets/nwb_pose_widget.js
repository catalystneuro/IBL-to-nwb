/**
 * Pose estimation video player widget.
 * Overlays DeepLabCut keypoints on streaming video with camera selection.
 *
 * Data format (from Python via JSON):
 * - pose_coordinates: {keypoint_name: [[x, y], null, [x, y], ...]}
 *   Each keypoint has an array of coordinates per frame, null for missing data
 * - timestamps: [t0, t1, t2, ...] array of frame timestamps
 */

const DISPLAY_WIDTH = 640;
const DISPLAY_HEIGHT = 512;

/**
 * Binary search for frame index closest to target time.
 * @param {number[]} timestamps - Sorted array of timestamps
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
 * Create an SVG icon element.
 * @param {"play" | "pause"} type - Icon type
 * @returns {SVGElement}
 */
function createIcon(type) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "currentColor");

  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  if (type === "play") {
    path.setAttribute("d", "M8 5v14l11-7z");
  } else {
    path.setAttribute("d", "M6 19h4V5H6v14zm8-14v14h4V5h-4z");
  }
  svg.appendChild(path);
  return svg;
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
  // Root wrapper with scoped class
  const wrapper = document.createElement("div");
  wrapper.classList.add("pose-widget");

  // Camera selector
  const cameraSelector = document.createElement("div");
  cameraSelector.classList.add("pose-widget__camera-selector");

  const cameraLabel = document.createElement("span");
  cameraLabel.textContent = "Camera:";
  cameraLabel.classList.add("pose-widget__camera-label");

  const cameraSelect = document.createElement("select");
  cameraSelect.classList.add("pose-widget__select");

  cameraSelector.appendChild(cameraLabel);
  cameraSelector.appendChild(cameraSelect);

  // Debug info
  const debugDiv = document.createElement("div");
  debugDiv.classList.add("pose-widget__debug");

  // Keypoint toggles container (holds both rows)
  const keypointTogglesWrapper = document.createElement("div");
  keypointTogglesWrapper.classList.add("pose-widget__keypoint-toggles-wrapper");

  // Utility buttons row (All/None)
  const utilityRow = document.createElement("div");
  utilityRow.classList.add("pose-widget__keypoint-toggles");

  // Keypoint buttons row
  const keypointRow = document.createElement("div");
  keypointRow.classList.add("pose-widget__keypoint-toggles");

  keypointTogglesWrapper.appendChild(utilityRow);
  keypointTogglesWrapper.appendChild(keypointRow);

  // Controls
  const controls = document.createElement("div");
  controls.classList.add("pose-widget__controls");

  const playPauseBtn = document.createElement("button");
  playPauseBtn.classList.add("pose-widget__button");
  playPauseBtn.appendChild(createIcon("play"));

  const seekBar = document.createElement("input");
  seekBar.type = "range";
  seekBar.min = 0;
  seekBar.max = 100;
  seekBar.value = 0;
  seekBar.classList.add("pose-widget__seekbar");

  const labelToggle = document.createElement("label");
  labelToggle.classList.add("pose-widget__label-toggle");
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
  videoContainer.classList.add("pose-widget__video-container");

  const video = document.createElement("video");
  video.classList.add("pose-widget__video");
  video.muted = true;
  video.playsInline = true;

  const canvas = document.createElement("canvas");
  canvas.width = DISPLAY_WIDTH;
  canvas.height = DISPLAY_HEIGHT;
  canvas.classList.add("pose-widget__canvas");

  // Loading spinner
  const loadingDiv = document.createElement("div");
  loadingDiv.classList.add("pose-widget__loading");
  const spinner = document.createElement("div");
  spinner.classList.add("pose-widget__spinner");
  loadingDiv.appendChild(spinner);

  videoContainer.appendChild(video);
  videoContainer.appendChild(canvas);
  videoContainer.appendChild(loadingDiv);

  let isPlaying = false;
  let animationId = null;
  let visibleKeypoints = { ...model.get("visible_keypoints") };

  /**
   * Update debug info display.
   * @param {number} frameIdx - Current frame index
   * @param {string} [extra] - Additional status text
   */
  function updateDebug(frameIdx, extra = "") {
    const camera = model.get("selected_camera");
    const timestamps = model.get("timestamps");
    const nFrames = timestamps ? timestamps.length : 0;
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
    const buttons = keypointRow.querySelectorAll("button[data-keypoint]");
    const metadata = model.get("keypoint_metadata");
    buttons.forEach((btn) => {
      const name = btn.dataset.keypoint;
      const isVisible = visibleKeypoints[name] !== false;
      const color = metadata[name]?.color || "#999";

      if (isVisible) {
        btn.classList.add("pose-widget__keypoint-toggle--active");
        btn.style.backgroundColor = color;
        btn.style.borderColor = color;
      } else {
        btn.classList.remove("pose-widget__keypoint-toggle--active");
        btn.style.backgroundColor = "";
        btn.style.borderColor = color;
      }
    });
  }

  function createKeypointToggles() {
    utilityRow.innerHTML = "";
    keypointRow.innerHTML = "";
    const metadata = model.get("keypoint_metadata");
    if (!metadata || Object.keys(metadata).length === 0) return;

    // All button
    const allBtn = document.createElement("button");
    allBtn.textContent = "All";
    allBtn.classList.add(
      "pose-widget__keypoint-toggle",
      "pose-widget__keypoint-toggle--utility"
    );
    allBtn.addEventListener("click", () => {
      for (const name of Object.keys(metadata)) visibleKeypoints[name] = true;
      model.set("visible_keypoints", { ...visibleKeypoints });
      model.save_changes();
      updateToggleStyles();
      drawPose();
    });

    // None button
    const noneBtn = document.createElement("button");
    noneBtn.textContent = "None";
    noneBtn.classList.add(
      "pose-widget__keypoint-toggle",
      "pose-widget__keypoint-toggle--utility"
    );
    noneBtn.addEventListener("click", () => {
      for (const name of Object.keys(metadata)) visibleKeypoints[name] = false;
      model.set("visible_keypoints", { ...visibleKeypoints });
      model.save_changes();
      updateToggleStyles();
      drawPose();
    });

    utilityRow.appendChild(allBtn);
    utilityRow.appendChild(noneBtn);

    // Individual keypoint buttons
    for (const [name, kp] of Object.entries(metadata)) {
      const btn = document.createElement("button");
      btn.textContent = name;
      btn.dataset.keypoint = name;
      btn.classList.add("pose-widget__keypoint-toggle");
      btn.style.borderColor = kp.color;
      btn.addEventListener("click", () => {
        visibleKeypoints[name] = !visibleKeypoints[name];
        model.set("visible_keypoints", { ...visibleKeypoints });
        model.save_changes();
        updateToggleStyles();
        drawPose();
      });
      keypointRow.appendChild(btn);
    }
    updateToggleStyles();
  }

  /**
   * Get current frame index based on video time.
   * @returns {number}
   */
  function getFrameIndex() {
    const timestamps = model.get("timestamps");
    if (!timestamps || timestamps.length === 0) return 0;
    return findFrameIndex(timestamps, timestamps[0] + video.currentTime);
  }

  /**
   * Draw pose keypoints on canvas overlay.
   */
  function drawPose() {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const metadata = model.get("keypoint_metadata");
    const coordinates = model.get("pose_coordinates");
    const timestamps = model.get("timestamps");
    const showLabels = model.get("show_labels");

    if (!coordinates || !timestamps || timestamps.length === 0) {
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

    for (const [name, coords] of Object.entries(coordinates)) {
      if (visibleKeypoints[name] === false) continue;

      const coord = coords[frameIdx];
      if (!coord) continue; // null means no data for this frame

      const x = coord[0] * scaleX;
      const y = coord[1] * scaleY;
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

  /**
   * Update play/pause button icon.
   * @param {boolean} playing - Current play state
   */
  function updatePlayPauseIcon(playing) {
    playPauseBtn.innerHTML = "";
    playPauseBtn.appendChild(createIcon(playing ? "pause" : "play"));
  }

  // Initialize
  populateCameraSelect();
  loadVideo();

  // Video loading state events
  video.addEventListener("loadstart", () => {
    videoContainer.classList.add("pose-widget__video-container--loading");
  });

  video.addEventListener("canplay", () => {
    videoContainer.classList.remove("pose-widget__video-container--loading");
  });

  video.addEventListener("loadedmetadata", () => {
    drawPose();
  });

  video.addEventListener("seeked", drawPose);
  video.addEventListener("timeupdate", drawPose);

  // Watch for pose data changes (when camera switches)
  function onPoseDataChange() {
    const timestamps = model.get("timestamps");
    seekBar.max = timestamps ? timestamps.length - 1 : 100;
    visibleKeypoints = { ...model.get("visible_keypoints") };
    createKeypointToggles();
    drawPose();
  }

  model.on("change:pose_coordinates", onPoseDataChange);
  model.on("change:keypoint_metadata", onPoseDataChange);

  cameraSelect.addEventListener("change", () => {
    if (isPlaying) {
      video.pause();
      updatePlayPauseIcon(false);
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
      if (animationId) cancelAnimationFrame(animationId);
    } else {
      video.play();
      animate();
    }
    isPlaying = !isPlaying;
    updatePlayPauseIcon(isPlaying);
  });

  seekBar.addEventListener("input", () => {
    const frameIdx = parseInt(seekBar.value);
    const timestamps = model.get("timestamps");
    if (timestamps && timestamps.length > 0) {
      video.currentTime = timestamps[frameIdx] - timestamps[0];
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
  wrapper.appendChild(keypointTogglesWrapper);
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
