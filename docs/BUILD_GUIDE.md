# Build Guide

- Python: 3.11+
- Install: pip install -r requirements.txt
- Env: create .env with API keys
- Run: streamlit run main.py
- Optional: docker build -t ai-gym-coach .
- Optional: docker run -p 8501:8501 ai-gym-coach

Step-by-Step Teaching Guide (25 Parts | ~10 min each):

Foundation and Setup
1	Introduction + Final Demo Preview (what we are building and why)
2	Project Setup (Python env, requirements, .env, first run)
3	Project Structure Deep Dive (core, detectors, services, pages, static)
4	Streamlit App Entry (main.py flow, page config, and landing boot)
5	Configuration Layer (workout config, constants, and shared keys)

Auth, State, and Persistence
6	SQLite Setup (exercise repository, schema init, and CRUD basics)
7	Login Wall (username session gate and user creation flow)
8	Session Defaults (initialize_session_state and state hygiene)
9	Workout Plan State (exercise selection, sets/reps goals, start/end lifecycle)

Vision Core
10	MediaPipe Concepts (landmarks, confidence scores, and tracking model)
11	Camera Input with WebRTC (stream setup and browser constraints)
12	Pose Landmarker Setup (model file loading and options tuning)
13	Video Processing Pipeline (recv loop, frame conversion, pose inference)
14	Skeleton and Overlay Rendering (connections, points, and exercise HUD)

Detector System
15	Base Detector Pattern (shared contract and reusable geometry logic)
16	Squat Detector Implementation (angles, depth, and rep counting)
17	Push-up + Curl Detectors (alignment, swing checks, and counters)
18	Shoulder Press + Lunge Detectors (extension, balance, and form checks)
19	Detector Integration (switching detectors by selected exercise)

Tracking and Voice Coaching
20	Metrics Sync + Goal Progress (queue drain, set completion, workout completion)
21	Feedback Engine Logic (cooldown, milestones, and form-triggered cues)
22	Voice Feedback Integration (LLM text generation + gTTS speech synthesis)
23	Voice Pipeline Completion (autoplay audio injection and session voice state)

UI, Delivery, and Wrap
24	Landing Page + Styling Polish (hero section, assets, and responsive design)
25  Host to streamlit cloud (end-to-end walkthrough and deployment notes)