/**
 * Multi-camera video player widget for synchronized playback.
 * Displays videos in a configurable grid layout with unified controls.
 *
 * @typedef {Object.<string, string>} VideoUrls - Mapping of video names to URLs
 * @typedef {string[][]} GridLayout - 2D array defining video grid (rows x cols)
 */

/**
 * Format seconds as MM:SS.ms string for session time display.
 * @param {number} seconds
 * @returns {string}
 */
function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10);
  return mins + ":" + secs.toString().padStart(2, "0") + "." + ms;
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
 * Render the multi-video player widget.
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
  wrapper.classList.add("video-widget");

  // Control bar
  const controls = document.createElement("div");
  controls.classList.add("video-widget__controls");

  const playPauseBtn = document.createElement("button");
  playPauseBtn.classList.add("video-widget__button");
  playPauseBtn.appendChild(createIcon("play"));
  playPauseBtn.appendChild(document.createTextNode(" Play All"));

  const seekBar = document.createElement("input");
  seekBar.type = "range";
  seekBar.min = 0;
  seekBar.max = 100;
  seekBar.value = 0;
  seekBar.classList.add("video-widget__seekbar");

  const timeLabel = document.createElement("span");
  timeLabel.textContent = "0:00.0 / 0:00.0";
  timeLabel.classList.add("video-widget__time-label");

  controls.appendChild(playPauseBtn);
  controls.appendChild(seekBar);
  controls.appendChild(timeLabel);

  // Grid container - using CSS Grid for proper 2D layout
  const gridContainer = document.createElement("div");
  gridContainer.classList.add("video-widget__grid");

  /** @type {HTMLVideoElement[]} */
  let videos = [];
  /** @type {HTMLDivElement[]} */
  let videoContainers = [];
  let isPlaying = false;
  let syncAnimationId = null;

  /**
   * Synchronize all videos to the master (first) video.
   * Corrects drift that occurs due to network latency and buffering differences.
   */
  function syncVideos() {
    if (videos.length < 2 || !isPlaying) {
      return;
    }

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

  /**
   * Update play/pause button content.
   * @param {boolean} playing - Current play state
   */
  function updatePlayPauseButton(playing) {
    playPauseBtn.innerHTML = "";
    playPauseBtn.appendChild(createIcon(playing ? "pause" : "play"));
    playPauseBtn.appendChild(
      document.createTextNode(playing ? " Pause All" : " Play All")
    );
  }

  /**
   * Get the session time offset for the first video in the grid.
   * This is the starting timestamp from the NWB file.
   */
  function getSessionTimeOffset() {
    const timestamps = model.get("video_timestamps");
    const gridLayout = model.get("grid_layout");
    // Find the first video in the grid that has timestamps
    for (const row of gridLayout) {
      for (const name of row) {
        if (timestamps[name] && timestamps[name].length > 0) {
          return timestamps[name][0];
        }
      }
    }
    return 0;
  }

  /**
   * Get the session end time (last timestamp) for the first video.
   */
  function getSessionEndTime() {
    const timestamps = model.get("video_timestamps");
    const gridLayout = model.get("grid_layout");
    for (const row of gridLayout) {
      for (const name of row) {
        if (timestamps[name] && timestamps[name].length > 1) {
          return timestamps[name][timestamps[name].length - 1];
        }
      }
    }
    return null; // Will fall back to video duration
  }

  function updateVideos() {
    gridContainer.innerHTML = "";
    videos = [];
    videoContainers = [];
    const urls = model.get("video_urls");
    const gridLayout = model.get("grid_layout");

    // Calculate grid dimensions from layout
    const numRows = gridLayout.length;
    const numCols = Math.max(...gridLayout.map((row) => row.length));

    gridContainer.style.gridTemplateColumns = "repeat(" + numCols + ", auto)";
    gridContainer.style.gridTemplateRows = "repeat(" + numRows + ", auto)";

    // Place videos in grid cells
    for (let rowIdx = 0; rowIdx < gridLayout.length; rowIdx++) {
      const row = gridLayout[rowIdx];
      for (let colIdx = 0; colIdx < row.length; colIdx++) {
        const name = row[colIdx];
        const url = urls[name];
        if (!url) continue; // Skip videos not in urls

        const videoCell = document.createElement("div");
        videoCell.classList.add("video-widget__video-cell");
        videoCell.style.gridRow = rowIdx + 1;
        videoCell.style.gridColumn = colIdx + 1;

        const videoContainer = document.createElement("div");
        videoContainer.classList.add("video-widget__video-container");
        videoContainers.push(videoContainer);

        const video = document.createElement("video");
        video.classList.add("video-widget__video");
        video.src = url;
        video.muted = true; // Mute to allow autoplay
        videos.push(video);

        // Loading spinner
        const loadingDiv = document.createElement("div");
        loadingDiv.classList.add("video-widget__loading");
        const spinner = document.createElement("div");
        spinner.classList.add("video-widget__spinner");
        loadingDiv.appendChild(spinner);

        // Video loading events
        video.addEventListener("loadstart", () => {
          videoContainer.classList.add("video-widget__video-container--loading");
        });
        video.addEventListener("canplay", () => {
          videoContainer.classList.remove(
            "video-widget__video-container--loading"
          );
        });

        videoContainer.appendChild(video);
        videoContainer.appendChild(loadingDiv);

        const label = document.createElement("p");
        label.textContent = name.replace("Video", "").replace("Camera", "");
        label.classList.add("video-widget__video-label");

        videoCell.appendChild(videoContainer);
        videoCell.appendChild(label);
        gridContainer.appendChild(videoCell);
      }
    }

    // Update seek bar max when metadata loads
    if (videos.length > 0) {
      videos[0].addEventListener("loadedmetadata", () => {
        seekBar.max = videos[0].duration;
        const offset = getSessionTimeOffset();
        const endTime = getSessionEndTime();
        const displayEnd = endTime !== null ? endTime : offset + videos[0].duration;
        timeLabel.textContent = formatTime(offset) + " / " + formatTime(displayEnd);
      });
      videos[0].addEventListener("timeupdate", () => {
        if (!seekBar.matches(":active")) {
          seekBar.value = videos[0].currentTime;
        }
        const offset = getSessionTimeOffset();
        const endTime = getSessionEndTime();
        const displayEnd = endTime !== null ? endTime : offset + videos[0].duration;
        const currentSessionTime = offset + videos[0].currentTime;
        timeLabel.textContent =
          formatTime(currentSessionTime) + " / " + formatTime(displayEnd);
      });
    }
  }

  playPauseBtn.addEventListener("click", () => {
    if (isPlaying) {
      videos.forEach((v) => v.pause());
      if (syncAnimationId) {
        cancelAnimationFrame(syncAnimationId);
        syncAnimationId = null;
      }
    } else {
      videos.forEach((v) => v.play());
      syncVideos(); // Start synchronization loop
    }
    isPlaying = !isPlaying;
    updatePlayPauseButton(isPlaying);
  });

  seekBar.addEventListener("input", () => {
    const time = parseFloat(seekBar.value);
    videos.forEach((v) => (v.currentTime = time));
  });

  model.on("change:video_urls", updateVideos);
  model.on("change:grid_layout", updateVideos);
  updateVideos();

  wrapper.appendChild(controls);
  wrapper.appendChild(gridContainer);
  el.appendChild(wrapper);

  // Cleanup function (called when widget is destroyed)
  return () => {
    if (syncAnimationId) {
      cancelAnimationFrame(syncAnimationId);
    }
  };
}

export default { render };
