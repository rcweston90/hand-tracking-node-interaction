#!/usr/bin/env python3
import os
os.environ['OPENCV_AVFOUNDATION_SKIP_AUTH'] = '1'

import cv2
from flask import Flask, render_template, Response, jsonify
import threading
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from mediapipe import Image, ImageFormat
import time
import numpy as np

app = Flask(__name__)
camera = None
lock = threading.Lock()

# Hand detection setup
options = vision.HandLandmarkerOptions(
    base_options=python.BaseOptions(model_asset_path='hand_landmarker.task'),
    num_hands=2,
    min_hand_detection_confidence=0.5,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.6  # Increased from 0.5 to reduce tracking drift
)
hand_landmarker = vision.HandLandmarker.create_from_options(options)

# Hand landmark connections
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),  # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),  # index
    (0, 9), (9, 10), (10, 11), (11, 12),  # middle
    (0, 13), (13, 14), (14, 15), (15, 16),  # ring
    (0, 17), (17, 18), (18, 19), (19, 20),  # pinky
]

# Store latest hand data
current_hand_data = {}

# Node placement state
class NodePlacementState:
    def __init__(self):
        self.node = None  # Single (x, y, z) tuple or None
        self.gesture_blocked = False  # When True, fist detection is ignored
        self.last_fist_time = {}  # Track last fist time per hand to prevent duplicates

    def reset(self):
        self.node = None
        self.gesture_blocked = False
        self.last_fist_time = {}

    def is_in_node_mode(self):
        return self.node is not None

    def try_place_node(self, hand_id, palm_pos, z_depth, current_time, confidence):
        """Place a single node on fist closure"""
        # If gesture is blocked or node exists, don't place
        if self.gesture_blocked or self.node is not None:
            return False

        # Debounce: 500ms between placement attempts
        last_time = self.last_fist_time.get(hand_id, 0)
        if current_time - last_time < 0.5:
            return False

        # Place node and block further gesture input
        self.last_fist_time[hand_id] = current_time
        self.node = (palm_pos[0], palm_pos[1], z_depth)
        self.gesture_blocked = True
        return True

    def reset_fist_hold(self, hand_id):
        """Reset fist hold counter when fist is released"""
        self.fist_hold_frames[hand_id] = 0

node_state = NodePlacementState()

def get_distance(p1, p2):
    """Calculate Euclidean distance between two points"""
    return ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5

def detect_fist(hand_landmarks):
    """Detect if hand is closed in a fist"""
    THUMB_TIP = 4
    INDEX_TIP = 8
    MIDDLE_TIP = 12
    RING_TIP = 16
    PINKY_TIP = 20
    PALM = 9

    palm = hand_landmarks[PALM]
    tips = [
        hand_landmarks[THUMB_TIP],
        hand_landmarks[INDEX_TIP],
        hand_landmarks[MIDDLE_TIP],
        hand_landmarks[RING_TIP],
        hand_landmarks[PINKY_TIP]
    ]

    fist_threshold = 0.08
    distances_to_palm = [get_distance((tip.x, tip.y), (palm.x, palm.y)) for tip in tips]

    # Simple fist detection: all fingers close to palm
    is_fist = all(d < fist_threshold for d in distances_to_palm)

    # Simplified confidence (avoid numpy operations)
    confidence = 0.8 if is_fist else 0.0

    return is_fist, (palm.x, palm.y), palm.z, confidence

def apply_sepia_filter(frame, intensity):
    """Apply sepia tone filter with adjustable intensity"""
    # Sepia tone matrix
    sepia_matrix = np.array([
        [0.272, 0.534, 0.131],
        [0.349, 0.686, 0.168],
        [0.393, 0.769, 0.189]
    ])

    # Apply sepia
    sepia = cv2.transform(frame, sepia_matrix)

    # Blend with original based on intensity
    result = cv2.addWeighted(frame, 1 - intensity, sepia, intensity, 0)
    return result

def draw_node(frame, node):
    """Draw single node as large circle on frame"""
    if node is None:
        return

    h, w, c = frame.shape
    x_norm, y_norm, z = node
    x = int(x_norm * w)
    y = int(y_norm * h)

    # Draw large circle for single node
    cv2.circle(frame, (x, y), 20, (0, 255, 255), -1)
    cv2.circle(frame, (x, y), 20, (255, 255, 0), 2)

def draw_status_text(frame, mode_text, node_present, fist_hold_progress=None):
    """Draw status text on frame"""
    h, w, c = frame.shape
    y_pos = 40
    cv2.putText(frame, mode_text, (20, y_pos),
               cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

def get_camera():
    global camera
    if camera is None:
        camera = cv2.VideoCapture(0)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return camera

def draw_hand_landmarks(frame, landmarks):
    """Draw hand skeleton on frame"""
    h, w, c = frame.shape

    # Draw circles at each landmark
    for landmark in landmarks:
        x = int(landmark.x * w)
        y = int(landmark.y * h)
        cv2.circle(frame, (x, y), 5, (0, 255, 0), -1)

    # Draw lines between connected landmarks
    for start, end in HAND_CONNECTIONS:
        start_pos = (int(landmarks[start].x * w), int(landmarks[start].y * h))
        end_pos = (int(landmarks[end].x * w), int(landmarks[end].y * h))
        cv2.line(frame, start_pos, end_pos, (255, 0, 0), 2)

def gen_frames():
    global current_hand_data, node_state
    cam = get_camera()
    while True:
        success, frame = cam.read()
        if not success:
            break

        # Flip horizontally for selfie view
        frame = cv2.flip(frame, 1)

        # Convert BGR to RGB for MediaPipe
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Create MediaPipe Image
        mp_image = Image(image_format=ImageFormat.SRGB, data=frame_rgb)

        # Run hand detection
        results = hand_landmarker.detect(mp_image)

        # Hand detection and node placement
        current_time = time.time()
        hand_data = []

        if results.hand_landmarks:
            for hand_idx, hand_landmarks in enumerate(results.hand_landmarks):
                # Detect fist
                is_fist, palm_pos, hand_z, confidence = detect_fist(hand_landmarks)

                # Only process fist input if gesture is not blocked
                if not node_state.gesture_blocked and is_fist:
                    node_state.try_place_node(hand_idx, palm_pos, hand_z, current_time, confidence)

        # Draw single node
        if node_state.node is not None:
            draw_node(frame, node_state.node)

        # Draw status text
        if node_state.gesture_blocked:
            mode_text = "Mode: Drag Mode"
        else:
            mode_text = "Mode: Ready to Place"

        draw_status_text(frame, mode_text, node_state.node is not None, None)

        with lock:
            current_hand_data = {'hands': hand_data, 'timestamp': current_time}

        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/hand_data')
def hand_data():
    with lock:
        return jsonify(current_hand_data)

@app.route('/node_state')
def get_node_state():
    """Get current node placement state"""
    # Convert single node to list format for compatibility with frontend
    nodes = [node_state.node] if node_state.node is not None else []
    return jsonify({
        'nodes': nodes,
        'node_count': 1 if node_state.node is not None else 0,
        'gesture_blocked': node_state.gesture_blocked,
        'in_node_mode': node_state.is_in_node_mode()
    })

@app.route('/reset', methods=['POST'])
def reset_nodes():
    """Reset node placement and sepia filter"""
    global node_state
    node_state.reset()
    return jsonify({'status': 'reset'})

@app.route('/update_node', methods=['POST'])
def update_node():
    """Update the single node position"""
    from flask import request
    data = request.json
    node_idx = data.get('index')
    x = data.get('x')
    y = data.get('y')

    # Only index 0 is valid for single node mode
    if node_idx == 0 and node_state.node is not None:
        # Keep z-depth, update x and y
        _, _, z = node_state.node
        node_state.node = (x, y, z)
        return jsonify({'status': 'updated'})

    return jsonify({'status': 'error', 'message': 'Invalid node index'}), 400

if __name__ == '__main__':
    print("Starting camera stream at http://localhost:5001")
    app.run(debug=False, host='0.0.0.0', port=5001)
