from flask import Flask, request, jsonify, render_template, Response
import cv2
import numpy as np
import threading
import time
import logging
import os

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Sensor data storage
sensor_data = {
    "gas": 0,
    "moisture": 0,
    "distance": 0,
    "wet": 0,
    "full": 0,
    "fill": 0,
    "status": "Initializing...",
    "ml_prediction": "No detection yet",
    "ml_confidence": 0,
    "ml_wet_detected": False
}

buzzer_muted = False

# ML Model variables
ml_model = None
camera = None
ml_running = False
last_prediction_time = 0
prediction_interval = 5  # seconds
current_frame = None
frame_lock = threading.Lock()
camera_ready = threading.Event()

def init_ml_model():
    """Initialize the ML model for waste classification"""
    global ml_model
    try:
        # Check if model file exists
        if not os.path.exists('waste_detection_model.h5'):
            logging.warning("❌ Model file 'waste_detection_model.h5' not found. Using mock predictions.")
            return False
            
        from tensorflow.keras.models import load_model
        ml_model = load_model('waste_detection_model.h5')
        logging.info("✅ ML Model loaded successfully!")
        return True
    except Exception as e:
        logging.error(f"❌ Error loading ML model: {e}")
        logging.info("🔄 Using mock predictions instead")
        return False

def init_camera():
    """Initialize the webcam"""
    global camera
    try:
        camera = cv2.VideoCapture(0)
        if camera.isOpened():
            # Test camera by capturing one frame
            ret, test_frame = camera.read()
            if ret:
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                camera.set(cv2.CAP_PROP_FPS, 30)
                logging.info("✅ Camera initialized successfully!")
                return True
            else:
                logging.error("❌ Camera test frame failed")
                return False
        else:
            logging.error("❌ Could not open camera")
            return False
    except Exception as e:
        logging.error(f"❌ Error initializing camera: {e}")
        return False

def mock_predict_waste(frame):
    """Mock prediction for testing when model is not available"""
    import random
    classes = ["Recyclable ♻️", "Organic/Wet 🍂"]
    class_name = random.choice(classes)
    confidence = round(random.uniform(0.6, 0.95), 2)
    is_wet = class_name == "Organic/Wet 🍂"
    return class_name, confidence, is_wet

def predict_waste(frame):
    """Predict waste type from frame"""
    global ml_model
    try:
        if ml_model is None:
            return mock_predict_waste(frame)
            
        # Preprocess the image
        img = cv2.resize(frame, (224, 224))
        img = img / 255.0  # Normalize
        img = np.expand_dims(img, axis=0)  # Add batch dimension
        
        # Make prediction
        predictions = ml_model.predict(img, verbose=0)
        predicted_class = np.argmax(predictions[0])
        confidence = np.max(predictions[0])
        
        # Map prediction to class name
        if predicted_class == 0:
            class_name = "Dry Waste ♻️"
            is_wet = False
        else:
            class_name = "Organic/Wet 🍂"
            is_wet = True
            
        return class_name, confidence, is_wet
    except Exception as e:
        logging.error(f"❌ Prediction error: {e}")
        return mock_predict_waste(frame)

def camera_capture_loop():
    """Continuously capture frames from camera"""
    global camera, current_frame, ml_running, camera_ready
    frame_count = 0
    
    while ml_running:
        try:
            if camera and camera.isOpened():
                ret, frame = camera.read()
                if ret:
                    with frame_lock:
                        current_frame = frame.copy()
                    frame_count += 1
                    
                    # Signal that camera is ready after first successful frame
                    if frame_count == 1:
                        camera_ready.set()
                        logging.info("✅ Camera capture started - first frame received")
                    
                    # Small delay to prevent excessive CPU usage
                    time.sleep(0.03)  # ~30 FPS
                else:
                    logging.error("❌ Failed to capture frame")
                    time.sleep(1)
            else:
                logging.warning("⚠️ Camera not available, waiting...")
                time.sleep(2)
        except Exception as e:
            logging.error(f"❌ Camera capture error: {e}")
            time.sleep(1)

def ml_processing_loop():
    """ML processing loop that analyzes frames every 5 seconds"""
    global ml_running, sensor_data, last_prediction_time, current_frame, camera_ready
    
    # Wait for camera to be ready
    logging.info("⏳ Waiting for camera to start...")
    camera_ready.wait(timeout=10)  # Wait up to 10 seconds for camera
    
    if not camera_ready.is_set():
        logging.warning("⚠️ Camera not ready after 10 seconds, continuing with mock data")
    
    while ml_running:
        try:
            current_time = time.time()
            
            # Check if it's time for next prediction (every 5 seconds)
            if current_time - last_prediction_time >= prediction_interval:
                if current_frame is not None:
                    # Make prediction on the current frame
                    with frame_lock:
                        frame_to_predict = current_frame.copy()
                    
                    class_name, confidence, is_wet = predict_waste(frame_to_predict)
                    
                    # Update sensor data
                    sensor_data["ml_prediction"] = class_name
                    sensor_data["ml_confidence"] = round(confidence * 100, 2)
                    sensor_data["ml_wet_detected"] = is_wet
                    
                    # If organic/wet waste detected, trigger alert
                    if is_wet and confidence > 0.7:  # Only if confident
                        logging.info(f"🚨 ML detected organic waste! Confidence: {confidence:.2%}")
                        # This would be sent to ESP32 in a real implementation
                    
                    last_prediction_time = current_time
                    logging.info(f"ML Prediction: {class_name} ({confidence:.2%})")
                else:
                    # Use mock data if no frame available
                    class_name, confidence, is_wet = mock_predict_waste(None)
                    sensor_data["ml_prediction"] = class_name
                    sensor_data["ml_confidence"] = round(confidence * 100, 2)
                    sensor_data["ml_wet_detected"] = is_wet
                    last_prediction_time = current_time
                    logging.info(f"Mock Prediction: {class_name} ({confidence:.2%})")
                
            time.sleep(0.1)  # Small delay
                
        except Exception as e:
            logging.error(f"❌ ML processing error: {e}")
            time.sleep(1)

def generate_frames():
    """Generate video frames for streaming - LIVE FEED"""
    global current_frame, camera_ready
    frame_count = 0
    
    # Wait for camera to be ready
    if not camera_ready.is_set():
        camera_ready.wait(timeout=5)
    
    while True:
        try:
            if current_frame is not None:
                # Create a copy of the current frame for streaming
                with frame_lock:
                    frame_copy = current_frame.copy()
                
                frame_count += 1
                
                # Add prediction info to frame
                prediction_text = f"{sensor_data['ml_prediction']} ({sensor_data['ml_confidence']}%)"
                cv2.putText(frame_copy, prediction_text, (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # Add timer until next prediction
                time_until_next = max(0, prediction_interval - (time.time() - last_prediction_time))
                timer_text = f"Next scan: {time_until_next:.1f}s"
                cv2.putText(frame_copy, timer_text, (10, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                # Add frame counter for debugging
                counter_text = f"Frame: {frame_count}"
                cv2.putText(frame_copy, counter_text, (10, 85), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                
                # Draw bounding box or other visual indicators
                if sensor_data['ml_wet_detected'] and sensor_data['ml_confidence'] > 70:
                    cv2.rectangle(frame_copy, (50, 50), (590, 430), (0, 0, 255), 3)
                    cv2.putText(frame_copy, "ORGANIC DETECTED!", (150, 400), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                
                # Encode frame as JPEG
                ret, buffer = cv2.imencode('.jpg', frame_copy)
                frame_bytes = buffer.tobytes()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            else:
                # Generate a waiting frame if no camera feed
                waiting_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                if camera_ready.is_set():
                    cv2.putText(waiting_frame, "No frame available", (200, 240), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                else:
                    cv2.putText(waiting_frame, "Starting camera...", (200, 240), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                ret, buffer = cv2.imencode('.jpg', waiting_frame)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                time.sleep(0.5)  # Shorter delay when waiting
                
        except Exception as e:
            logging.error(f"Error generating frame: {e}")
            time.sleep(1)

# Initialize ML system when first request comes in
@app.before_request
def initialize_ml():
    global ml_running
    if not hasattr(app, 'ml_initialized'):
        app.ml_initialized = True
        ml_running = True
        
        # Initialize hardware first
        camera_success = init_camera()
        ml_success = init_ml_model()
        
        # Start camera capture thread
        camera_thread = threading.Thread(target=camera_capture_loop)
        camera_thread.daemon = True
        camera_thread.start()
        
        # Start ML processing thread
        ml_thread = threading.Thread(target=ml_processing_loop)
        ml_thread.daemon = True
        ml_thread.start()
        
        logging.info("✅ ML system started successfully!")

# Routes
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/video_feed")
def video_feed():
    return Response(generate_frames(), 
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/update")
def update():
    global sensor_data
    try:
        sensor_data["gas"] = request.args.get("gas", type=int) or 0
        sensor_data["moisture"] = request.args.get("moisture", type=int) or 0
        sensor_data["distance"] = request.args.get("distance", type=float) or 0
        sensor_data["wet"] = request.args.get("wet", type=int) or 0
        sensor_data["full"] = request.args.get("full", type=int) or 0
        sensor_data["fill"] = request.args.get("fill", type=int) or 0
        sensor_data["status"] = request.args.get("status", default="Running")

        return "OK"
    except Exception as e:
        return f"ERR: {e}", 400

@app.route("/sensor-data")
def sensor_data_api():
    return jsonify(sensor_data)

@app.route("/buzzer", methods=["GET", "POST"])
def buzzer():
    global buzzer_muted

    if request.method == "GET":
        return jsonify({"stop": buzzer_muted})

    state = request.form.get("state")
    if state == "stop":
        buzzer_muted = True
    elif state == "start":
        buzzer_muted = False

    return "OK"

@app.route("/ml-status")
def ml_status():
    """Return ML model status"""
    global last_prediction_time, prediction_interval
    status = {
        "ml_loaded": ml_model is not None,
        "camera_available": camera is not None and camera.isOpened(),
        "camera_ready": camera_ready.is_set(),
        "ml_running": ml_running,
        "current_prediction": sensor_data["ml_prediction"],
        "confidence": sensor_data["ml_confidence"],
        "wet_detected": sensor_data["ml_wet_detected"],
        "time_until_next_scan": max(0, prediction_interval - (time.time() - last_prediction_time)),
        "has_frame": current_frame is not None
    }
    return jsonify(status)

@app.route("/restart-camera")
def restart_camera():
    """Endpoint to restart camera if needed"""
    global camera
    try:
        if camera:
            camera.release()
        camera = cv2.VideoCapture(0)
        if camera.isOpened():
            return jsonify({"status": "Camera restarted successfully"})
        else:
            return jsonify({"status": "Failed to restart camera"}), 500
    except Exception as e:
        return jsonify({"status": f"Error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)