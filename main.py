# =============================================================================
# main.py — Hand Gesture Controller (Python / PC Side)
#
# What this script does:
#   1. Opens your webcam using OpenCV
#   2. Uses Google MediaPipe to find and track your hand in real time
#   3. Reads the Y-position of your index finger tip (landmark #8)
#   4. Detects whether your hand is OPEN or a FIST
#   5. Sends a compact data packet over USB serial to your Arduino
#      FORMAT: "brightness,GESTURE\n"  e.g. "128,OPEN\n" or "0,FIST\n"
# =============================================================================

import cv2
import mediapipe as mp
import serial
import serial.tools.list_ports
import time
import numpy as np

# -----------------------------------------------------------------------------
# CONFIGURATION — Edit these values to match your setup
# -----------------------------------------------------------------------------
SERIAL_PORT = "COM3"        # Windows: "COM3", "COM4", etc.
                             # Mac/Linux: "/dev/ttyUSB0" or "/dev/ttyACM0"
BAUD_RATE   = 9600           # Must match the baud rate in your Arduino code
SEND_DELAY  = 0.05           # Seconds between serial sends (50ms = 20 times/sec)
# -----------------------------------------------------------------------------

# --- Initialize MediaPipe Hands ---
# MediaPipe is Google's library for detecting 21 3D landmarks on a hand.
mp_hands   = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# max_num_hands=1 tells MediaPipe to only track one hand (faster & simpler)
hands = mp_hands.Hands(
    static_image_mode=False,   # False = video stream mode (much faster)
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.6
)

# --- Helper: Detect Open Hand vs Fist ---
def get_gesture(hand_landmarks, handedness):
    """
    Analyzes the 21 hand landmarks to determine the gesture.
    
    Strategy: For each of the 4 fingers (not thumb), check if the
    FINGERTIP landmark is HIGHER on screen than the KNUCKLE landmark.
    (Remember: in image coordinates, Y=0 is the TOP of the screen.)
    
    If 3 or more fingers are extended, it's an OPEN hand.
    Otherwise, it's a FIST.
    """
    lm = hand_landmarks.landmark  # shorthand for the list of 21 landmarks

    # Landmark indices for fingertips and their corresponding middle knuckles (PIP joint)
    # Index: 8,  Middle: 12,  Ring: 16,  Pinky: 20
    # PIP knuckles: 6, 10, 14, 18
    finger_tips = [8, 12, 16, 20]
    finger_pips = [6, 10, 14, 18]

    extended_fingers = 0
    for tip_id, pip_id in zip(finger_tips, finger_pips):
        # If tip Y is LESS THAN pip Y, the finger is pointing up (extended)
        # because a smaller Y value means higher up on screen
        if lm[tip_id].y < lm[pip_id].y:
            extended_fingers += 1

    return "OPEN" if extended_fingers >= 3 else "FIST"


# --- Open the Serial Port ---
# We wrap this in a try/except so the program gives a helpful error
# instead of crashing silently if the port is wrong.
ser = None
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # IMPORTANT: Wait 2 seconds for Arduino to reset after connecting
    print(f"[OK] Connected to Arduino on {SERIAL_PORT}")
except serial.SerialException as e:
    print(f"[ERROR] Could not open serial port '{SERIAL_PORT}'.")
    print(f"        Reason: {e}")
    print(f"        See Step 4 of the guide to find your correct port name.")
    # We'll continue running so you can still see the webcam window,
    # but no data will be sent.


# --- Open the Webcam ---
cap = cv2.VideoCapture(0)  # 0 = your default/built-in webcam
if not cap.isOpened():
    print("[ERROR] Could not open webcam. Is another application using it?")
    exit()

print("[OK] Webcam opened. Press 'Q' to quit.")

last_send_time = 0  # Tracks when we last sent data, to control send rate

# =============================================================================
# MAIN LOOP
# =============================================================================
while True:
    ret, frame = cap.read()  # Read one frame from the webcam
    if not ret:
        print("[ERROR] Failed to read frame from webcam.")
        break

    # --- Flip the frame horizontally ---
    # This creates a "mirror" effect, which feels more natural to use.
    frame = cv2.flip(frame, 1)
    frame_height, frame_width, _ = frame.shape

    # --- Prepare image for MediaPipe ---
    # MediaPipe needs RGB format, but OpenCV gives us BGR by default.
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # --- Run Hand Detection ---
    results = hands.process(rgb_frame)

    # Default values sent when no hand is detected
    brightness = 0
    gesture    = "NONE"

    # --- Process Hand Landmarks (if a hand was found) ---
    if results.multi_hand_landmarks:
        for hand_landmarks, handedness_info in zip(
            results.multi_hand_landmarks,
            results.multi_handedness
        ):
            # -- Draw the skeleton overlay on screen --
            # This is what lets you see the 21 dots and connecting lines!
            mp_drawing.draw_landmarks(
                frame,
                hand_landmarks,
                mp_hands.HAND_CONNECTIONS  # Draws the lines between landmarks
            )

            # -- Calculate Brightness from Index Finger Y-position --
            # Landmark #8 is the tip of the index finger.
            index_finger_tip_y = hand_landmarks.landmark[8].y
            # landmark.y is a normalized value from 0.0 (top) to 1.0 (bottom)
            # We INVERT it (1.0 - y) so that:
            #   Hand HIGH on screen  → high brightness (255)
            #   Hand LOW on screen   → low brightness  (0)
            inverted_y = 1.0 - index_finger_tip_y
            # Map the 0.0–1.0 range to an integer 0–255 for Arduino's analogWrite()
            brightness = int(np.clip(inverted_y * 255, 0, 255))

            # -- Detect Gesture --
            handedness_label = handedness_info.classification[0].label
            gesture = get_gesture(hand_landmarks, handedness_label)

            # -- Draw Info Text on Screen --
            cv2.putText(frame, f"Brightness: {brightness}", (10, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, f"Gesture: {gesture}", (10, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

    else:
        # No hand detected — show a helpful message on screen
        cv2.putText(frame, "No hand detected", (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    # --- Send Data Over Serial ---
    # We throttle sends with SEND_DELAY to avoid flooding the Arduino's buffer.
    current_time = time.time()
    if ser and ser.is_open and (current_time - last_send_time) > SEND_DELAY:
        # Build the packet string: "brightness,GESTURE\n"
        packet = f"{brightness},{gesture}\n"
        try:
            ser.write(packet.encode("utf-8"))  # Convert string to bytes and send
            last_send_time = current_time
        except serial.SerialException as e:
            print(f"[WARNING] Lost serial connection: {e}")

    # --- Display the Webcam Window ---
    cv2.imshow("Hand Gesture Controller — Press Q to quit", frame)

    # --- Quit when 'Q' is pressed ---
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

# =============================================================================
# CLEANUP
# =============================================================================
print("Shutting down...")
cap.release()
cv2.destroyAllWindows()
if ser and ser.is_open:
    ser.close()
    print("Serial port closed.")