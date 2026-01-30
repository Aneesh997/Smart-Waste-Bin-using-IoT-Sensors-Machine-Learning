# Smart Waste Bin using IoT Sensors & Machine Learning

## 📌 Overview
The **Smart Waste Bin using IoT Sensors & Machine Learning** is an AI-enabled waste management system designed to automatically monitor bin fill level, detect wet/dry waste, sense harmful gases, and display real-time data on a web dashboard.  
The system reduces manual effort, prevents overflow, and improves waste segregation using IoT and machine learning.

---

## 🚀 Features
- Real-time bin fill-level monitoring using ultrasonic sensor  
- Wet and dry waste detection using moisture sensor  
- Odor and gas detection using MQ-135 sensor  
- AI-based waste classification using CNN  
- Live web dashboard for monitoring sensor data  
- Smart alerts using LEDs and buzzer  
- Remote monitoring via Wi-Fi  

---

## 🧠 Technologies Used

### Hardware
- ESP32-S3 (Wi-Fi enabled microcontroller)
- Ultrasonic Sensor (HC-SR04)
- Capacitive Moisture Sensor
- MQ-135 Gas Sensor
- USB Webcam

### Software & Tools
- Python 3
- Flask (Backend & API)
- TensorFlow / Keras (Machine Learning)
- OpenCV (Image Processing)
- HTML, CSS, JavaScript (Frontend)
- Arduino IDE (ESP32 Programming)

---

## 🏗️ System Architecture
1. **Sensor Layer**  
   ESP32 reads data from ultrasonic, moisture, and gas sensors.

2. **Processing Layer**  
   - Sensor data sent to Flask server via Wi-Fi  
   - CNN model classifies waste using webcam images  

3. **Presentation Layer**  
   - Web dashboard displays live values and alerts  
   - User can mute or enable buzzer remotely  

---

## ⚙️ How It Works
1. ESP32 connects to Wi-Fi and calibrates sensors  
2. Sensors continuously monitor waste conditions  
3. Data is sent to Flask server every second  
4. CNN model classifies waste using camera input  
5. Dashboard displays:
   - Fill percentage  
   - Gas level  
   - Moisture level  
   - Waste type  
6. Alerts are triggered when bin is full or wet waste is detected  

---

## 🖥️ Local Setup

### Clone the Repository
```bash
git clone https://github.com/your-username/smart-waste-bin.git
cd smart-waste-bin
