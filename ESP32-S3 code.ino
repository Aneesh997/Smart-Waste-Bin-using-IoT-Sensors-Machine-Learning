#include <WiFi.h>
#include <HTTPClient.h>

// ===== WIFI =====
const char* ssid = "alphi";
const char* password = "asr98765";
String serverURL = "http://192.168.55.95:5000/update";
String buzzerURL = "http://192.168.55.95:5000/buzzer";
String mlStatusURL = "http://192.168.55.95:5000/ml-status";

// ===== PINS =====
#define MQ135_PIN 5
#define MOISTURE_PIN 6
#define TRIG_PIN 10
#define ECHO_PIN 11
#define BUZZER_PIN 39
#define RED_LED_PIN 40     // Wet waste LED (Sensor + ML)
#define YELLOW_LED_PIN 38  // Bin full LED

// ===== GAS CALIBRATION =====
int baselineGas = -1;
long gasSum = 0;
int gasCount = 0;
bool gasDone = false;

bool buzzerMuted = false;
String deviceStatus = "Calibrating";
unsigned long lastSend = 0;
unsigned long lastMLCheck = 0;
unsigned long lastBeep = 0;
const unsigned long MLCheckInterval = 3000; // Check ML status every 3 seconds
const unsigned long beepInterval = 2000;    // Beep every 2 seconds when detection is active

// ML Status variables
bool mlWetDetected = false;
int mlConfidence = 0;
String mlPrediction = "Unknown";

// Buzzer state variables
bool beepActive = false;
unsigned long beepStartTime = 0;
const unsigned long beepDuration = 300;
int beepPattern = 0; // 0=idle, 1=sensor, 2=ml, 3=mixed, 4=full

// ===== Distance Baseline fixed =====
float baselineDistance = 20.0;  // cm (EMPTY BIN)
float minDist = 5.0;            // cm (FULL)
float maxDist = 23.0;           // also full case

void connectWiFi() {
  WiFi.begin(ssid, password);
  Serial.print("WiFi:");
  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    delay(350);
  }
  Serial.println(" ✅ Connected");
  Serial.println(WiFi.localIP());
}

float getDist() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(3);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long d = pulseIn(ECHO_PIN, HIGH);
  return d * 0.034 / 2;
}

void checkBuzzerCommand() {
  HTTPClient http;
  http.begin(buzzerURL);
  int code = http.GET();

  if (code == 200) {
    String res = http.getString();
    buzzerMuted = res.indexOf("\"stop\": true") > 0;
    if (buzzerMuted) {
      noTone(BUZZER_PIN);
      beepActive = false;
    }
  }
  http.end();
}

void checkMLStatus() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(mlStatusURL);
  int code = http.GET();

  if (code == 200) {
    String response = http.getString();
    
    // Parse JSON response (simplified parsing)
    if (response.indexOf("\"wet_detected\": true") > 0) {
      mlWetDetected = true;
    } else {
      mlWetDetected = false;
    }
    
    // Extract confidence (simplified)
    int confidenceStart = response.indexOf("\"confidence\":") + 12;
    int confidenceEnd = response.indexOf(",", confidenceStart);
    if (confidenceStart > 12 && confidenceEnd > confidenceStart) {
      String confStr = response.substring(confidenceStart, confidenceEnd);
      mlConfidence = confStr.toInt();
    }
    
    // Extract prediction
    int predStart = response.indexOf("\"current_prediction\":\"") + 21;
    int predEnd = response.indexOf("\"", predStart);
    if (predStart > 21 && predEnd > predStart) {
      mlPrediction = response.substring(predStart, predEnd);
    }
    
    Serial.println("ML Status: " + mlPrediction + " (" + String(mlConfidence) + "%) - Wet: " + String(mlWetDetected));
  } else {
    Serial.println("Failed to get ML status: " + String(code));
  }
  http.end();
}

void updateBuzzer() {
  if (buzzerMuted) {
    noTone(BUZZER_PIN);
    beepActive = false;
    return;
  }

  unsigned long currentTime = millis();
  
  // Check if it's time for the next beep
  if (currentTime - lastBeep >= beepInterval && beepPattern > 0) {
    
    switch(beepPattern) {
      case 1: // Sensor detection - single beep
        tone(BUZZER_PIN, 1200);
        beepActive = true;
        beepStartTime = currentTime;
        Serial.println("🔊 Buzzer: Sensor detection");
        break;
        
      case 2: // ML detection - double beep
        tone(BUZZER_PIN, 1500);
        beepActive = true;
        beepStartTime = currentTime;
        Serial.println("🔊 Buzzer: ML detection");
        break;
        
      case 3: // Mixed detection - alternating beeps
        tone(BUZZER_PIN, (currentTime % 400 < 200) ? 1200 : 1500);
        beepActive = true;
        beepStartTime = currentTime;
        Serial.println("🔊 Buzzer: Mixed detection");
        break;
        
      case 4: // Full bin - triple beep
        if ((currentTime - lastBeep) % 600 < 200) {
          tone(BUZZER_PIN, 1000);
          beepActive = true;
        } else {
          noTone(BUZZER_PIN);
          beepActive = false;
        }
        Serial.println("🔊 Buzzer: Bin full");
        break;
    }
    
    lastBeep = currentTime;
  }
  
  // Stop beep after duration
  if (beepActive && (currentTime - beepStartTime >= beepDuration)) {
    noTone(BUZZER_PIN);
    beepActive = false;
  }
}

void updateLEDs(bool sensorWet, bool full, bool mlWet) {
  // RED LED: Wet waste detection (Sensor OR ML)
  bool anyWetDetection = sensorWet || mlWet;
  
  if (anyWetDetection) {
    // Blink red LED for any wet waste detection (500ms interval)
    static unsigned long lastBlink = 0;
    static bool ledState = false;
    
    if (millis() - lastBlink > 500) {
      ledState = !ledState;
      digitalWrite(RED_LED_PIN, ledState ? HIGH : LOW);
      lastBlink = millis();
    }
  } else {
    digitalWrite(RED_LED_PIN, LOW);
  }
  
  // YELLOW LED: Bin full (solid on)
  digitalWrite(YELLOW_LED_PIN, full ? HIGH : LOW);
}

void sendToServer(int gas, int moist, float dist, bool wet, bool full, int fill) {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();

  HTTPClient http;
  http.setReuse(true);

  String status = deviceStatus;
  status.replace(" ", "%20");

  // Combine sensor and ML detection for wet waste status
  bool combinedWet = wet || mlWetDetected;

  String url = serverURL +
    "?gas=" + gas +
    "&moisture=" + moist +
    "&distance=" + String(dist, 2) +
    "&wet=" + (combinedWet ? "1" : "0") +
    "&full=" + (full ? "1" : "0") +
    "&fill=" + fill +
    "&status=" + status;

  http.begin(url);
  int httpCode = http.GET();
  
  if (httpCode == 200) {
    Serial.println("✅ Data sent to server");
  } else {
    Serial.println("❌ Failed to send data: " + String(httpCode));
  }
  
  http.end();
}

void setup() {
  Serial.begin(115200);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(YELLOW_LED_PIN, OUTPUT);

  // Initialize LEDs
  digitalWrite(RED_LED_PIN, LOW);
  digitalWrite(YELLOW_LED_PIN, LOW);

  connectWiFi();
  
  Serial.println("🚀 Smart Bin System Started");
  Serial.println("📊 Sensors: MQ135, Moisture, Ultrasonic");
  Serial.println("🤖 AI: Integrated ML Waste Classification");
  Serial.println("🔴 RED LED: Wet Waste (Sensor + ML)");
  Serial.println("🟡 YELLOW LED: Bin Full");
}

void loop() {
  checkBuzzerCommand();

  // Check ML status every 3 seconds
  if (millis() - lastMLCheck >= MLCheckInterval) {
    checkMLStatus();
    lastMLCheck = millis();
  }

  int gas = analogRead(MQ135_PIN);
  int moist = analogRead(MOISTURE_PIN);
  float dist = getDist();

  // GAS baseline calibration first
  if (!gasDone) {
    gasSum += gas;
    gasCount++;

    if (gasCount >= 20) {
      baselineGas = gasSum / gasCount;
      gasDone = true;
      deviceStatus = "Ready";
      Serial.println("✅ Gas Calibrated: " + String(baselineGas));
    }

    sendToServer(gas, moist, dist, false, false, 0);
    delay(500);
    return;
  }

  // ===== Bin Fill Logic =====
  int fill;

  if (dist > maxDist) fill = 100;      // Over-range = full
  else if (dist < minDist) fill = 100; // Low = trash touching sensor = full
  else {
    fill = map(dist, baselineDistance, minDist, 0, 100);
    fill = constrain(fill, 0, 100);
  }

  // Sensor-based wet waste detection
  bool sensorWet = (moist < 3200) || (gas >= baselineGas + 500);
  bool full = (fill >= 95) || dist > maxDist || dist < minDist;

  // Combine sensor and ML detection
  bool anyWetDetection = sensorWet || mlWetDetected;
  bool bothDetections = sensorWet && mlWetDetected;

  // Update LEDs with combined status
  updateLEDs(sensorWet, full, mlWetDetected);

  // Determine buzzer pattern with priority
  if (full) {
    beepPattern = 4; // Full bin - highest priority
  } 
  else if (bothDetections) {
    beepPattern = 3; // Mixed detection
  }
  else if (mlWetDetected && mlConfidence > 70) {
    beepPattern = 2; // ML detection
  }
  else if (sensorWet) {
    beepPattern = 1; // Sensor detection
  }
  else {
    beepPattern = 0; // No detection
    noTone(BUZZER_PIN);
    beepActive = false;
  }

  // Update buzzer state
  updateBuzzer();

  // Send data to server every 800ms
  if (millis() - lastSend > 800) {
    sendToServer(gas, moist, dist, anyWetDetection, full, fill);
    lastSend = millis();
  }

  // Enhanced serial output
  Serial.printf("Gas:%d Moist:%d Dist:%.2f Fill:%d ", gas, moist, dist, fill);
  Serial.printf("SensorWet:%d ML_Wet:%d(%d%%) ", sensorWet, mlWetDetected, mlConfidence);
  Serial.printf("Full:%d BuzzerPattern:%d Muted:%d\n", full, beepPattern, buzzerMuted);

  delay(100); // Small delay for stability
}