/**
 * Multi-camera video player widget for synchronized playback.
 * Displays videos in a configurable grid layout with unified controls.
 *
 * @typedef {Object.<string, string>} VideoUrls - Mapping of video names to URLs
 * @typedef {string[][]} GridLayout - 2D array defining video grid (rows x cols)
 */

/**
 * Format seconds as MM:SS string.
 * @param {number} seconds
 * @returns {string}
 */
function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return mins + ":" + secs.toString().padStart(2, "0");
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
  const wrapper = document.createElement("div");
  wrapper.style.fontFamily = "sans-serif";

  // Control bar
  const controls = document.createElement("div");
  controls.style.marginBottom = "10px";
  controls.style.display = "flex";
  controls.style.alignItems = "center";
  controls.style.gap = "10px";

  const playPauseBtn = document.createElement("button");
  playPauseBtn.textContent = "Play All";
  playPauseBtn.style.padding = "8px 16px";
  playPauseBtn.style.fontSize = "14px";
  playPauseBtn.style.cursor = "pointer";

  const seekBar = document.createElement("input");
  seekBar.type = "range";
  seekBar.min = 0;
  seekBar.max = 100;
  seekBar.value = 0;
  seekBar.style.flex = "1";

  const timeLabel = document.createElement("span");
  timeLabel.textContent = "0:00 / 0:00";
  timeLabel.style.fontSize = "12px";
  timeLabel.style.minWidth = "100px";

  controls.appendChild(playPauseBtn);
  controls.appendChild(seekBar);
  controls.appendChild(timeLabel);

  // Grid container - using CSS Grid for proper 2D layout
  const gridContainer = document.createElement("div");
  gridContainer.style.display = "grid";
  gridContainer.style.gap = "10px";
  gridContainer.style.justifyContent = "center";

  /** @type {HTMLVideoElement[]} */
  let videos = [];
  let isPlaying = false;

  function updateVideos() {
    gridContainer.innerHTML = "";
    videos = [];
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

        const videoContainer = document.createElement("div");
        videoContainer.style.textAlign = "center";
        videoContainer.style.gridRow = rowIdx + 1;
        videoContainer.style.gridColumn = colIdx + 1;

        const video = document.createElement("video");
        video.width = 320;
        video.height = 240;
        video.style.display = "block";
        video.style.backgroundColor = "#000";
        video.src = url;
        video.muted = true; // Mute to allow autoplay
        videos.push(video);

        const label = document.createElement("p");
        label.textContent = name.replace("Video", "").replace("Camera", "");
        label.style.fontWeight = "bold";
        label.style.margin = "5px 0";

        videoContainer.appendChild(video);
        videoContainer.appendChild(label);
        gridContainer.appendChild(videoContainer);
      }
    }

    // Update seek bar max when metadata loads
    if (videos.length > 0) {
      videos[0].addEventListener("loadedmetadata", () => {
        seekBar.max = videos[0].duration;
        timeLabel.textContent = "0:00 / " + formatTime(videos[0].duration);
      });
      videos[0].addEventListener("timeupdate", () => {
        if (!seekBar.matches(":active")) {
          seekBar.value = videos[0].currentTime;
        }
        timeLabel.textContent =
          formatTime(videos[0].currentTime) +
          " / " +
          formatTime(videos[0].duration);
      });
    }
  }

  playPauseBtn.addEventListener("click", () => {
    if (isPlaying) {
      videos.forEach((v) => v.pause());
      playPauseBtn.textContent = "Play All";
    } else {
      videos.forEach((v) => v.play());
      playPauseBtn.textContent = "Pause All";
    }
    isPlaying = !isPlaying;
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
}

export default { render };
