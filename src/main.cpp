// =============================================================================
// main.cpp — Hand Gesture Controller (Arduino / Hardware Side)
//
// What this code does:
//   1. Listens on the USB serial port for data from the Python script
//   2. Safely parses packets in the format: "128,OPEN\n"
//   3. Uses analogWrite() to set LED brightness via PWM (0–255)
//   4. Displays the current gesture and brightness on the OLED screen
//
// Wiring reminder:
//   LED (+) anode     → Digital Pin 9  (PWM)
//   LED (−) cathode   → 220Ω resistor  → GND
//   OLED VCC          → 5V
//   OLED GND          → GND
//   OLED SDA          → A4
//   OLED SCL          → A5
// =============================================================================

#include <Arduino.h>
#include <Wire.h>              // Built-in: handles I2C communication for the OLED
#include <Adafruit_GFX.h>      // Adafruit's core graphics library
#include <Adafruit_SSD1306.h>  // Adafruit's driver for the SSD1306 OLED chip

// --- OLED Display Configuration ---
// These values tell the library the exact screen dimensions and I2C address.
#define SCREEN_WIDTH  128   // Pixels wide
#define SCREEN_HEIGHT  64   // Pixels tall
#define OLED_RESET     -1   // -1 = share the Arduino's reset pin (most common)
#define OLED_I2C_ADDR 0x3C  // Default I2C address for most 0.96" OLEDs.
                             // If your screen shows nothing, try 0x3D instead.

// Create the display object. We'll call it 'display' throughout the code.
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// --- Pin Configuration ---
const int LED_PIN = 9;  // Must be a PWM pin (marked with ~ on the Uno)

// --- Serial Parsing Variables ---
// We read incoming serial data character-by-character into a buffer.
// This is the safe, non-blocking approach — the Arduino never "waits" for data.
String serialBuffer = "";        // Accumulates characters until we get "\n"
bool   newDataReady = false;     // Flag: a complete packet has arrived

// --- State Variables ---
// These hold the most recently received values, displayed and acted on each loop.
int    ledBrightness = 0;
String currentGesture = "Waiting...";

// =============================================================================
// SETUP — Runs once when the Arduino powers on or is reset
// =============================================================================
void setup() {
    // Start serial communication at 9600 baud — MUST match Python script
    Serial.begin(9600);

    // Configure the LED pin as an output
    pinMode(LED_PIN, OUTPUT);
    analogWrite(LED_PIN, 0);  // Start with LED off

    // --- Initialize the OLED Display ---
    // SSD1306_SWITCHCAPVCC = generate display voltage from the 3.3V pin internally
    if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR)) {
        // If the display fails to start, we can't show an error on screen,
        // so we halt the program with a fast LED blink to signal the problem.
        Serial.println("ERROR: SSD1306 OLED not found. Check wiring & I2C address.");
        while (true) {
            digitalWrite(LED_PIN, HIGH); delay(100);
            digitalWrite(LED_PIN, LOW);  delay(100);
        }
    }

    // Clear any leftover content from the display's memory
    display.clearDisplay();

    // Show a startup splash screen so you know the OLED is working
    display.setTextSize(1);           // Small text (6x8 pixels per character)
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(20, 20);
    display.println("Gesture Controller");
    display.setCursor(30, 36);
    display.println("Ready! Run Python");
    display.display();  // IMPORTANT: nothing shows until you call display()

    delay(2000);  // Show splash for 2 seconds
}

// =============================================================================
// READ SERIAL — Called each loop to check for incoming data
//
// Non-blocking design: We read one character at a time using Serial.read(),
// only if Serial.available() tells us data is waiting. This means the main
// loop() never "freezes" waiting for data — it keeps running at full speed.
// =============================================================================
void readSerialData() {
    while (Serial.available() > 0) {
        char inChar = (char)Serial.read();  // Read one character

        if (inChar == '\n') {
            // Newline = end of packet. Set the flag and stop reading.
            newDataReady = true;
            break;
        } else {
            // Append the character to our growing buffer string
            serialBuffer += inChar;

            // Safety cap: discard oversized buffers to prevent memory issues
            // A valid packet like "255,OPEN" is at most ~10 characters
            if (serialBuffer.length() > 20) {
                serialBuffer = "";
            }
        }
    }
}

// =============================================================================
// PARSE PACKET — Splits "128,OPEN" into brightness (128) and gesture ("OPEN")
//
// The packet format is: "<number>,<word>"
// We use indexOf(',') to find the comma, then grab what's before and after it.
// =============================================================================
void parsePacket(String packet) {
    int commaIndex = packet.indexOf(',');

    // Validate: a comma must exist and must not be the first or last character
    if (commaIndex <= 0 || commaIndex >= (int)packet.length() - 1) {
        Serial.print("WARN: Malformed packet ignored: ");
        Serial.println(packet);
        return;  // Skip this bad packet, don't update anything
    }

    // Extract the brightness value (everything before the comma)
    String brightnessStr = packet.substring(0, commaIndex);
    int parsedBrightness = brightnessStr.toInt();

    // Clamp brightness to valid range [0, 255] just in case
    ledBrightness = constrain(parsedBrightness, 0, 255);

    // Extract the gesture string (everything after the comma)
    currentGesture = packet.substring(commaIndex + 1);
    currentGesture.trim();  // Remove any stray whitespace or carriage returns
}

// =============================================================================
// UPDATE DISPLAY — Redraws the OLED with the latest values
//
// We call clearDisplay() each time to start fresh, then draw all the text,
// and finish with display.display() to push the buffer to the physical screen.
// =============================================================================
void updateDisplay() {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);

    // --- Line 1: Title / Header ---
    display.setTextSize(1);
    display.setCursor(20, 0);
    display.println("Hand Gesture Control");

    // --- Separator line ---
    display.drawLine(0, 10, SCREEN_WIDTH - 1, 10, SSD1306_WHITE);

    // --- Line 2: Gesture name (large text) ---
    display.setTextSize(2);  // 2x size = 12x16 pixels per character
    display.setCursor(0, 16);
    display.println(currentGesture);

    // --- Line 3: Brightness value ---
    display.setTextSize(1);
    display.setCursor(0, 40);
    display.print("Brightness: ");
    display.println(ledBrightness);

    // --- Line 4: Visual brightness bar ---
    // Map brightness (0–255) to a bar width (0–116 pixels)
    int barWidth = map(ledBrightness, 0, 255, 0, 116);
    display.drawRect(0, 54, 118, 8, SSD1306_WHITE);   // Outer border rectangle
    display.fillRect(1, 55, barWidth, 6, SSD1306_WHITE); // Filled portion

    // Push the completed frame buffer to the physical OLED screen
    display.display();
}

// =============================================================================
// LOOP — Runs forever after setup()
// =============================================================================
void loop() {
    // Step 1: Check for and accumulate incoming serial characters
    readSerialData();

    // Step 2: If a complete packet arrived, parse it and update state
    if (newDataReady) {
        parsePacket(serialBuffer);

        // Clear the buffer and flag for the next packet
        serialBuffer = "";
        newDataReady = false;

        // Step 3: Apply the new brightness to the physical LED
        // analogWrite() outputs a PWM signal — at 128, the LED is ~50% bright
        analogWrite(LED_PIN, ledBrightness);

        // Step 4: Refresh the OLED screen with new values
        updateDisplay();
    }
}