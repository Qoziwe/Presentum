# 📽 Presentum

> **Self-hosted real-time presentation engine with a bidirectional remote console and zero external cloud dependencies.**

**Presentum** solves the headache of delivering presentations in lecture halls and meeting rooms. Instead of handing over flash drives, transferring heavy slide decks to the lecturer, or relying on third-party cloud platforms with unpredictable latency, you simply share a single URL. The presentation display opens instantly on the intended slide, while you control the flow directly from your smartphone without ever looking down.

---

## 🎯 Workflow

1. **At Home:** Open `/admin`, upload a multi-page PDF or a set of image slides. The server automatically slices pages, arranges order indexes, and persists the state. You leave it preset, for example, on slide #5.
2. **In the Lecture Hall:** Share your public link with the lecturer: `https://presentum.andatra.space/presentation`.
3. **On the Projector:** The lecturer opens the link — the screen **immediately** renders slide #5 on a pure black background in full-screen scale with zero delay (powered by Server-Side Rendering).
4. **In Your Hand:** Open `/admin/control` on your smartphone. You get massive touch buttons `◀` and `▶`, an active slide counter, a live thumbnail of the current slide, and tactile haptic vibration feedback on every slide switch.

---

## ✨ Key Features

- **Real-Time Bidirectional Channel:** Instantaneous slide switching response (< 10 ms) backed by WebSockets (`Flask-SocketIO`).
- **Server-Side Rendering (SSR):** The initial slide image and counter are rendered directly into the raw HTML payload by Jinja2. Even under poor cellular connectivity, the projector shows the correct slide without blank white frames or waiting for client JS execution.
- **Zero-CDN Autonomy:** The `socket.io.min.js` client library is bundled directly within the repository. The application runs fully offline or behind strict campus firewalls without reaching external CDNs.
- **Universal Slide Ingestion:**
  - Standard graphics: `PNG`, `JPG`, `WEBP`, `GIF`.
  - Presentation `PDF`: Multi-page documents are automatically sliced into high-definition PNGs using native C++ Poppler (`pdftoppm -png -r 150`) with automatic temporary file cleanup.
- **Flexible Deck Management:**
  - Positional insertion: Insert slides at any specific index (e.g., between slide 3 and 4) with automatic order shifting.
  - Granular deletion with physical disk purge and index realignment.
  - Live broadcast toggle: Activate any slide directly from the admin grid via background AJAX without reloading the dashboard.
  - One-click nuclear reset: Wipe all deck assets and state cleanly.
- **Ergonomic Mobile Remote Controller:**
  - Oversized touch targets designed for blind one-handed thumb navigation during a talk.
  - Haptic feedback vibration (`navigator.vibrate`) on touch.
  - In-hand slide preview: Keep track of what is projected behind your back without turning around.
  - Full keyboard mapping (`Space`, `PageDown`, `PageUp`, Left/Right arrow keys).
- **Audience Stage View:**
  - Responsive letterboxing tailored for any aspect ratio or projector (`object-fit: contain`).
  - Smooth visual cross-fade transition between slides.
  - Dedicated `F` hotkey for instant browser fullscreen toggle.

---

## 🛠 Tech Stack

- **Backend:** Python 3.12+, Flask, Flask-SocketIO, Gunicorn (gthread worker model), simple-websocket.
- **Database:** SQLite + Flask-SQLAlchemy (atomic order-shifting transactions, concurrency timeout protection).
- **PDF Processing Engine:** Poppler (`pdftoppm`).
- **Frontend:** Modern HTML5 / CSS3 / Vanilla JavaScript, bundled Socket.IO Client.
- **Networking & Deployment:** Cloudflare Zero Trust Tunnel, WSS/HTTPS edge termination.

---

## 🚀 Quick Start

### 1. System Dependencies

- **Arch Linux:**
  ```bash
  sudo pacman -S python poppler
  ```
- **Debian / Ubuntu:**
  ```bash
  sudo apt update && sudo apt install -y python3 python3-venv poppler-utils
  ```
- **Android (Termux):**
  ```bash
  pkg update && pkg install -y python poppler
  ```

### 2. Installation

```bash
git clone https://github.com/Qoziwe/Presentum.git
cd Presentum

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # For fish shell: source venv/bin/activate.fish

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration (`.env`)

Create a `.env` file in the project root:

```ini
SECRET_KEY=your_super_secret_hex_key
ADMIN_PASSWORD=your_secure_password
PORT=5004
DATABASE_URL=sqlite:///database.db
```

### 4. Running

- **Development Mode:**
  ```bash
  python app.py
  ```
- **Production Mode (Gunicorn):**
  ```bash
  gunicorn -w 1 --threads 100 -b 127.0.0.1:5004 app:app
  ```

---

## 🔒 Security

- All management endpoints (`/admin/api/*`), uploads, and socket mutation events (`admin_next`, `admin_prev`, `admin_goto`) require authenticated administrator session tokens.
- Audience displays on `/presentation` operate in strict read-only mode and can only receive broadcasted `slide_state` payloads.

---

## 📄 License

MIT License © 2026 [Qoziwe](https://github.com/Qoziwe)
