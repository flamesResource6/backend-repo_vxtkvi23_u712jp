"""
Voice-Assisted Student Helper (Terminal-based)

Features:
- Listens via microphone (SpeechRecognition + PyAudio)
- Speaks responses offline (pyttsx3)
- Tells date & time
- Opens common websites (YouTube, Google, Gmail) or any URL
- Tells weather (Open-Meteo API, no key) with graceful fallback
- Creates quick reminders (stored in memory and saved to reminders.txt)
- Answers simple academic questions (Wikipedia summary)
- Tells jokes or motivational lines
- Friendly, clear responses, and also prints text for debugging
- Clean, beginner-friendly, single-file code with comments

How to run (quick):
1) Ensure microphone access is allowed on your OS.
2) Install dependencies:  pip install -r requirements.txt
3) Start the assistant:  python voice_assistant.py
4) Say: "hey assistant" or just speak your command after the prompt.
5) Say "exit", "quit", or "stop" to close.
"""

# -----------------------------
# Import necessary libraries
# -----------------------------
import os
import re
import sys
import json
import time
import queue
import random
import webbrowser
import traceback
from datetime import datetime

import requests  # For weather and web APIs
import speech_recognition as sr  # For microphone input / speech-to-text
import pyttsx3  # For offline text-to-speech

try:
    import wikipedia  # For simple academic questions
except Exception:  # If import fails at runtime, we will handle gracefully
    wikipedia = None


# -----------------------------
# Initialize recognizer + speaker
# -----------------------------
recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True  # adapts to background noise

# Initialize TTS engine (offline)
engine = pyttsx3.init()
# Set a friendly, clear voice (try to pick a female or default voice)
voices = engine.getProperty("voices")
if voices:
    # pick the first available voice for consistency
    engine.setProperty("voice", voices[0].id)
engine.setProperty("rate", 175)  # slightly slower than default for clarity
engine.setProperty("volume", 1.0)


# -----------------------------
# Helper: Speak text aloud and also print for debugging
# -----------------------------
def speak(text: str) -> None:
    """Convert text to speech and print for debugging."""
    text = str(text).strip()
    if not text:
        return
    print(f"Assistant: {text}")
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        # If TTS fails, at least the text is printed
        print(f"[TTS Error] {e}")


# -----------------------------
# Helper: Listen to voice input from default microphone
# -----------------------------

def listen(timeout: float = 5.0, phrase_time_limit: float = 8.0) -> str:
    """Listen via microphone and return recognized text using Google Web Speech API.

    - timeout: seconds to wait for phrase to start
    - phrase_time_limit: max seconds to record once phrase starts

    Returns lowercased string of the recognized text.
    Raises ValueError on unclear audio.
    """
    with sr.Microphone() as source:
        # Reduce ambient noise for a short moment
        try:
            recognizer.adjust_for_ambient_noise(source, duration=0.6)
        except Exception:
            pass
        print("Listening...")
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except sr.WaitTimeoutError:
            raise ValueError("No speech detected (timeout). Please try again.")
    try:
        # Using Google's free recognizer (internet required). For offline STT you may plug in other engines.
        text = recognizer.recognize_google(audio)
        return text.lower().strip()
    except sr.UnknownValueError:
        raise ValueError("Sorry, I couldn't understand that. Please repeat.")
    except sr.RequestError as e:
        # If Google API is not reachable
        raise ValueError(f"Speech service unavailable: {e}")


# -----------------------------
# Core abilities
# -----------------------------

def tell_time() -> str:
    now = datetime.now().strftime("%I:%M %p")
    return f"It's {now}."


def tell_date() -> str:
    today = datetime.now().strftime("%A, %B %d, %Y")
    return f"Today is {today}."


def open_website(command: str) -> str:
    """Open common sites or any URL mentioned."""
    # Common shortcuts
    sites = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "gmail": "https://mail.google.com",
        "stackoverflow": "https://stackoverflow.com",
        "wikipedia": "https://wikipedia.org",
        "github": "https://github.com",
    }
    for key, url in sites.items():
        if key in command:
            webbrowser.open(url)
            return f"Opening {key}."

    # If a full URL is spoken
    url_pattern = r"(https?://\S+)"
    match = re.search(url_pattern, command)
    if match:
        url = match.group(1)
        webbrowser.open(url)
        return "Opening the link you mentioned."

    # If user said "open X"
    m = re.search(r"open\s+([a-z0-9\.-]+)" , command)
    if m:
        target = m.group(1)
        # Try as known site name
        if target in sites:
            webbrowser.open(sites[target])
            return f"Opening {target}."
        # Try to construct a URL
        possible = f"https://{target}.com"
        webbrowser.open(possible)
        return f"Trying to open {possible}."

    return "Please specify which website to open. Try saying 'open YouTube' or 'open google.com'."


def get_weather(command: str) -> str:
    """Fetch current weather using Open-Meteo (no API key) with geocoding.
    If city not provided, default to your location name 'your city'.
    """
    # Extract city name after phrases like: weather in X / what's the weather in X
    city = None
    m = re.search(r"weather\s+(in|at|for)\s+([a-zA-Z\s\-]+)", command)
    if m:
        city = m.group(2).strip()

    if not city:
        # Try detect single word after 'in'
        m2 = re.search(r"in\s+([a-zA-Z\s\-]+)$", command)
        if m2:
            city = m2.group(1).strip()

    if not city:
        # Default demo city
        city = "New York"

    try:
        # 1) Geocode the city
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        geo_params = {"name": city, "count": 1, "language": "en", "format": "json"}
        g = requests.get(geo_url, params=geo_params, timeout=8)
        g.raise_for_status()
        data = g.json()
        if not data.get("results"):
            return f"Sorry, I couldn't find weather info for {city}."
        item = data["results"][0]
        lat, lon = item["latitude"], item["longitude"]
        pretty_name = item.get("name", city)

        # 2) Fetch current weather
        weather_url = "https://api.open-meteo.com/v1/forecast"
        w = requests.get(weather_url, params={
            "latitude": lat,
            "longitude": lon,
            "current_weather": True
        }, timeout=8)
        w.raise_for_status()
        wdata = w.json()
        cw = wdata.get("current_weather")
        if not cw:
            return f"Weather data not available right now for {pretty_name}."

        temp = cw.get("temperature")
        wind = cw.get("windspeed")
        return f"Current weather in {pretty_name}: {temp} degrees Celsius with wind speed {wind} kilometers per hour."
    except Exception:
        # Fallback dummy data
        return f"Right now, I can't reach the weather service. But my guess is it's a pleasant study weather in {city}!"


# Simple in-memory reminders (also persist to a text file for convenience)
REMINDERS_FILE = "reminders.txt"
reminders = []  # list of dicts: {"text": str, "timestamp": iso}


def load_reminders():
    global reminders
    if os.path.exists(REMINDERS_FILE):
        try:
            with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    # naive parse: timestamp | text
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        reminders.append({"timestamp": parts[0].strip(), "text": parts[1].strip()})
        except Exception:
            pass


def save_reminder(text: str) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    reminders.append({"timestamp": ts, "text": text})
    try:
        with open(REMINDERS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts} | {text}\n")
    except Exception:
        pass


def add_reminder_from_command(command: str) -> str:
    # Capture text after keywords
    m = re.search(r"(remind me to|add reminder|remember that|note that)\s+(.+)", command)
    if m:
        note = m.group(2).strip()
        save_reminder(note)
        return f"Got it. I'll remember: {note}."
    # fallback: take everything after 'reminder'
    m2 = re.search(r"reminder\s+(.+)", command)
    if m2:
        note = m2.group(1).strip()
        save_reminder(note)
        return f"Added reminder: {note}."
    return "Please tell me what to remember. For example: 'remind me to submit the assignment'."


def list_reminders() -> str:
    if not reminders:
        return "You have no reminders yet."
    lines = [f"{i+1}. {r['text']} (added {r['timestamp']})" for i, r in enumerate(reminders[-5:])]
    return "Here are your latest reminders: " + " | ".join(lines)


# Simple academic Q&A using Wikipedia summary

def academic_answer(command: str) -> str:
    if wikipedia is None:
        return "Wikipedia module isn't available right now."
    # Extract topic after common phrases
    m = re.search(r"(who is|what is|define|tell me about)\s+(.+)", command)
    topic = None
    if m:
        topic = m.group(2).strip()
    else:
        # fallback: try last word(s) after 'about'
        m2 = re.search(r"about\s+(.+)", command)
        if m2:
            topic = m2.group(1).strip()

    if not topic:
        return "Please tell me the topic. For example: 'what is photosynthesis' or 'who is Alan Turing'."

    try:
        wikipedia.set_lang("en")
        summary = wikipedia.summary(topic, sentences=2, auto_suggest=True, redirect=True)
        return summary
    except wikipedia.DisambiguationError as e:
        # Pick the first option to keep it simple
        try:
            summary = wikipedia.summary(e.options[0], sentences=2)
            return summary
        except Exception:
            return "That topic has multiple meanings. Please be more specific."
    except wikipedia.PageError:
        return "I couldn't find a good summary for that topic. Try another question."
    except Exception:
        return "Sorry, I had trouble reaching Wikipedia right now."


JOKES = [
    "Why do Java developers wear glasses? Because they don't C#.",
    "I told my computer I needed a break, and now it won't stop sending KitKat ads.",
    "Why was the math book sad? Because it had too many problems.",
]

MOTIVATION = [
    "Small steps, every day. You've got this!",
    "Progress over perfection. Keep going!",
    "Your future self will thank you for studying today.",
]


def tell_joke() -> str:
    return random.choice(JOKES)


def motivate() -> str:
    return random.choice(MOTIVATION)


# -----------------------------
# Main interaction loop
# -----------------------------

def greet():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        greet = "Good morning"
    elif 12 <= hour < 17:
        greet = "Good afternoon"
    elif 17 <= hour < 22:
        greet = "Good evening"
    else:
        greet = "Hello"
    speak(f"{greet}! I'm your student helper. How can I assist you today?")


def print_help() -> str:
    return (
        "Here are some things you can say: "
        " time | date | open YouTube | open Google | open Gmail | open <site> | "
        " what's the weather in <city> | add reminder <text> | list reminders | "
        " what is <topic> | who is <person> | tell me about <subject> | joke | motivate | help | exit"
    )


def handle_command(cmd: str) -> str:
    """Route the command to the correct action and return the text response."""
    if not cmd:
        return "I didn't catch that. Please try again."

    # Exit commands
    if any(word in cmd for word in ["exit", "quit", "stop", "goodbye"]):
        return "__EXIT__"

    # Help
    if "help" in cmd or "what can you do" in cmd:
        return print_help()

    # Time / Date
    if "time" in cmd and not "timer" in cmd:
        return tell_time()
    if "date" in cmd or "day" in cmd:
        return tell_date()

    # Open websites
    if "open" in cmd or "youtube" in cmd or "gmail" in cmd or "google" in cmd:
        return open_website(cmd)

    # Weather
    if "weather" in cmd:
        return get_weather(cmd)

    # Reminders
    if "remind" in cmd or "reminder" in cmd or "remember" in cmd:
        return add_reminder_from_command(cmd)
    if "list reminders" in cmd or "show reminders" in cmd:
        return list_reminders()

    # Academic questions
    if any(k in cmd for k in ["what is", "who is", "define", "tell me about", "explain"]):
        return academic_answer(cmd)

    # Jokes / Motivation
    if "joke" in cmd:
        return tell_joke()
    if "motivate" in cmd or "motivation" in cmd or "inspire" in cmd:
        return motivate()

    # Fallback
    return "I'm here to help with time, date, opening sites, weather, reminders, and simple questions. Say 'help' to see examples."


def main():
    # Load previous reminders if any
    load_reminders()

    greet()
    speak("Say 'help' if you want to know what I can do.")

    while True:
        try:
            try:
                command = listen()
            except ValueError as e:
                # couldn't hear / understand
                speak(str(e))
                continue

            print(f"You said: {command}")  # Debug print

            response = handle_command(command)
            if response == "__EXIT__":
                speak("Goodbye! Happy studying.")
                break

            speak(response)

        except KeyboardInterrupt:
            speak("Stopping now. Goodbye!")
            break
        except Exception as e:
            # Catch-all to avoid crashing the loop
            print("[Error]", e)
            traceback.print_exc()
            speak("I ran into an error. Please try again.")
            time.sleep(0.5)


if __name__ == "__main__":
    main()
