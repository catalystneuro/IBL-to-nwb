/**
 * Pose estimation video player widget.
 * Overlays DeepLabCut keypoints on streaming video with camera selection.
 *
 * Data format (from Python via JSON):
 * - all_camera_data: {camera_name: {keypoint_metadata, pose_coordinates, timestamps}}
 *   All camera data is loaded upfront for instant switching
 * - pose_coordinates: {keypoint_name: [[x, y], null, [x, y], ...]}
 *   Each keypoint has an array of coordinates per frame, null for missing data
 * - timestamps: [t0, t1, t2, ...] array of frame timestamps
 */

const DISPLAY_WIDTH = 640;
const DISPLAY_HEIGHT = 512;

/**
 * Format seconds as MM:SS.ms string for session time display.
 * @param {number} seconds - Time in seconds
 * @returns {string} Formatted time string
 */
function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10);
  return mins + ":" + secs.toString().padStart(2, "0") + "." + ms;
}

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
 * @param {Object} context - Provided by anywidget
 * @param {Object} context.model - Proxy to Python traitlets
 * @param {HTMLElement} context.el - The DOM element where the widget should render
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

  // Keypoint toggles container
  const keypointTogglesWrapper = document.createElement("div");
  keypointTogglesWrapper.classList.add("pose-widget__keypoint-toggles-wrapper");

  const utilityRow = document.createElement("div");
  utilityRow.classList.add("pose-widget__keypoint-toggles");

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

  const timeLabel = document.createElement("span");
  timeLabel.classList.add("pose-widget__time-label");
  timeLabel.textContent = "0:00.0 / 0:00.0";

  const labelToggle = document.createElement("label");
  labelToggle.classList.add("pose-widget__label-toggle");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = model.get("show_labels");
  labelToggle.appendChild(checkbox);
  labelToggle.appendChild(document.createTextNode("Labels"));

  controls.appendChild(playPauseBtn);
  controls.appendChild(seekBar);
  controls.appendChild(timeLabel);
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

  videoContainer.appendChild(video);
  videoContainer.appendChild(canvas);

  let isPlaying = false;
  let animationId = null;
  let visibleKeypoints = { ...model.get("visible_keypoints") };

  /**
   * Get current camera's data from all_camera_data.
   */
  function getCurrentCameraData() {
    const camera = model.get("selected_camera");
    const allData = model.get("all_camera_data");
    return allData[camera] || null;
  }

  /**
   * Update debug info display.
   */
  function updateDebug(frameIdx, extra = "") {
    const camera = model.get("selected_camera");
    const data = getCurrentCameraData();
    const nFrames = data?.timestamps?.length || 0;
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

  /**
   * Update time label with NWB session timestamps.
   * Shows current time / total duration in session time (not video-relative).
   */
  function updateTimeLabel(frameIdx) {
    const data = getCurrentCameraData();
    const timestamps = data?.timestamps;
    if (!timestamps || timestamps.length === 0) {
      timeLabel.textContent = "0:00.0 / 0:00.0";
      return;
    }
    const currentTime = timestamps[frameIdx] || timestamps[0];
    const endTime = timestamps[timestamps.length - 1];
    timeLabel.textContent = formatTime(currentTime) + " / " + formatTime(endTime);
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
    const data = getCurrentCameraData();
    const metadata = data?.keypoint_metadata || {};
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
    const data = getCurrentCameraData();
    const metadata = data?.keypoint_metadata || {};
    if (Object.keys(metadata).length === 0) return;

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
   */
  function getFrameIndex() {
    const data = getCurrentCameraData();
    const timestamps = data?.timestamps;
    if (!timestamps || timestamps.length === 0) return 0;
    return findFrameIndex(timestamps, timestamps[0] + video.currentTime);
  }

  /**
   * Draw pose keypoints on canvas overlay.
   */
  function drawPose() {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const data = getCurrentCameraData();
    if (!data) {
      updateDebug(0, "No pose data");
      return;
    }

    const metadata = data.keypoint_metadata;
    const coordinates = data.pose_coordinates;
    const timestamps = data.timestamps;
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
    updateTimeLabel(frameIdx);
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

  function updatePlayPauseIcon(playing) {
    playPauseBtn.innerHTML = "";
    playPauseBtn.appendChild(createIcon(playing ? "pause" : "play"));
  }

  /**
   * Switch to a new camera - updates UI immediately since all data is preloaded.
   */
  function switchCamera() {
    // Update seek bar max for new camera
    const data = getCurrentCameraData();
    seekBar.max = data?.timestamps?.length - 1 || 100;

    // Recreate keypoint toggles for new camera
    createKeypointToggles();

    // Load new video URL
    loadVideo();

    // Draw immediately (data is already available)
    drawPose();
  }

  // Initialize
  populateCameraSelect();
  loadVideo();
  createKeypointToggles();

  // Set initial seek bar max
  const initialData = getCurrentCameraData();
  if (initialData?.timestamps) {
    seekBar.max = initialData.timestamps.length - 1;
  }

  video.addEventListener("loadedmetadata", drawPose);
  video.addEventListener("seeked", drawPose);
  video.addEventListener("timeupdate", drawPose);

  cameraSelect.addEventListener("change", () => {
    if (isPlaying) {
      video.pause();
      updatePlayPauseIcon(false);
      if (animationId) cancelAnimationFrame(animationId);
      isPlaying = false;
    }

    model.set("selected_camera", cameraSelect.value);
    model.save_changes();
    switchCamera();
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
    const data = getCurrentCameraData();
    const timestamps = data?.timestamps;
    if (timestamps && timestamps.length > 0) {
      video.currentTime = timestamps[frameIdx] - timestamps[0];
    }
  });

  checkbox.addEventListener("change", () => {
    model.set("show_labels", checkbox.checked);
    model.save_changes();
    drawPose();
  });

  updateDebug(0, "Ready");
  updateTimeLabel(0);

  wrapper.appendChild(cameraSelector);
  wrapper.appendChild(debugDiv);
  wrapper.appendChild(keypointTogglesWrapper);
  wrapper.appendChild(controls);
  wrapper.appendChild(videoContainer);
  el.appendChild(wrapper);

  // Cleanup function
  return () => {
    if (animationId) {
      cancelAnimationFrame(animationId);
    }
  };
}

export default { render };
