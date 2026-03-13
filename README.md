# Hand Tracking - Single Node Interaction

A real-time hand gesture detection system that lets you place and manipulate 3D nodes using hand gestures captured via webcam.

## Features

- **Hand Detection**: Real-time hand pose detection using MediaPipe
- **Fist Gesture**: Close your fist to place a node at your palm position
- **Node Dragging**: Click and drag nodes with your mouse to reposition them
- **Gesture Blocking**: After placing a node, gesture input is blocked until you reset
- **Reset**: Click the Reset button to clear the node and enable gesture placement again

## Requirements

- Python 3.8+
- macOS with webcam access
- Dependencies: Flask, OpenCV, MediaPipe

## Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Download the MediaPipe hand landmarker model:
   ```bash
   wget https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker.task
   ```

## Usage

Start the server:
```bash
python3 app.py
```

Open your browser to `http://localhost:5001`

### Interaction Flow

1. **Placement Mode** (green light on): Raise your hand to the camera
2. **Place Node**: Close your fist and hold for ~100ms—a cyan circle appears at your palm
3. **Drag Mode**: Gesture input is now blocked. Click the node and drag it around
4. **Reset**: Click "Reset Node" to clear and return to placement mode

## Architecture

- **Backend**: Flask server with OpenCV and MediaPipe
- **Frontend**: HTML/CSS/JavaScript with canvas-based node visualization
- **Hand Detection**: MediaPipe HandLandmarker with confidence-based fist detection
- **State Management**: Single-node placement model with gesture blocking

## Performance

- Hand detection: ~30-50ms per frame
- Optimized fist detection with early exit on non-matches
- Smooth 30fps video stream with minimal latency

## Known Issues

- Requires explicit camera permissions on macOS (System Preferences > Security & Privacy > Camera)
- Some USB cameras may have compatibility issues—test with Photo Booth first

## Future Improvements

- Multi-node support
- Different gesture types (open hand, pinch, etc.)
- 3D perspective transformation
- Recording and playback

## License

MIT
