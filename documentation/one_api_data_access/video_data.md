# Video Data Utilities

Functions for accessing video frames and metadata from IBL recordings.

## Function Reference

| Function/Class | Module | Description |
|----------------|--------|-------------|
| `VideoStreamer` | `ibllib.io.video` | Stream video from HTTP server |
| `get_video_frame(path, frame_number)` | `ibllib.io.video` | Get single frame |
| `get_video_frames_preload(vid, frame_numbers)` | `ibllib.io.video` | Bulk load multiple frames |
| `get_video_meta(path, one=None)` | `ibllib.io.video` | Get video metadata |

## Example Usage

```python
from ibllib.io.video import get_video_frame, get_video_meta, VideoStreamer

# Get video metadata
meta = get_video_meta('/path/to/video.mp4')
print(f"Duration: {meta['duration']}, FPS: {meta['fps']}")

# Get a single frame
frame = get_video_frame('/path/to/video.mp4', frame_number=100)

# Stream from remote server
streamer = VideoStreamer('/path/to/remote/video.mp4')
frame = streamer.get_frame(100)
```

## Metadata Fields

`get_video_meta()` returns a dictionary with:

| Field | Description |
|-------|-------------|
| `duration` | Video length in seconds |
| `fps` | Frames per second |
| `width` | Frame width in pixels |
| `height` | Frame height in pixels |
| `size` | File size in bytes |

## Pros and Cons

**Pros:**
- Memory-efficient frame-by-frame access
- Works with both local and remote videos
- Bulk loading for efficiency when needed

**Cons:**
- Network latency for remote access
- Requires authentication for some servers
- Large videos may have slow random access

## When to Use

- Extracting specific frames for analysis
- Building video processing pipelines
- Accessing video metadata without loading full video

## Source

`ibllib.io.video`
