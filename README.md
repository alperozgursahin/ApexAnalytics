# ApexAnalytics - F1 Telemetry Analysis Platform

ApexAnalytics is a web-based data analysis platform that captures, processes, and visualizes live UDP telemetry data from the F1® 24 game. It is built with Python, Django, and Chart.js to provide detailed insights into race sessions.

---

## ✨ Features

-   **Live Data Capture**: Listens for UDP packets from the F1® 24 game and logs them into `.jsonl` files for persistent storage.
-   **Intelligent Data Import**: Efficiently parses log files and imports session data into the database for analysis.
-   **Interactive Dashboard**: Displays high-level statistics like total sessions, laps driven, and most-driven tracks.
-   **Advanced Session Filtering**: The session list page allows users to filter recorded sessions by **Track**, **Session Type** (Practice, Qualifying, Race, etc.), and **Game Mode** (Career, Grand Prix, Online).
-   **In-Depth Session Analysis**: Provides a detailed breakdown for each session, including:
    -   **Lap Times Chart**: An interactive bar chart showing all lap times, enriched with **tyre compound icons** displayed directly above each bar.
    -   **Telemetry Graphs**: Detailed analysis of the fastest lap, visualizing Speed, RPM, Throttle, and Brake inputs.
    -   **Strategy Analysis Chart**: An advanced graph displaying ERS battery levels, ERS deployment modes, and DRS activation zones throughout the lap.
    -   **Fuel Usage Graph**: Tracks fuel consumption over the course of the session.

---

## 🛠️ Tech Stack

-   **Backend**: Python, Django
-   **Frontend**: HTML, CSS, JavaScript, Chart.js
-   **Data Parsing**: Python `ctypes` library
-   **Database**: Django ORM (SQLite by default)
