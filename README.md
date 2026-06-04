# BookBot — Context-Aware Reading Assistant

BookBot is an immersive, gamified reading assistant that reads your books and discusses them with you — without ever spoiling the future chapters.

## 🔗 Key URLs

| Service | URL | Purpose |
| --- | --- | --- |
| **Frontend** | [http://localhost:5173](http://localhost:5173) | Main application UI |
| **Backend API** | [http://localhost:8000](http://localhost:8000) | Backend service root |
| **API Documentation** | [http://localhost:8000/docs](http://localhost:8000/docs) | Interactive Swagger UI docs |

---

## 🚀 Getting Started

### 1. Backend Setup
1. Navigate to the `bookbot` directory.
2. Install dependencies: `pip install -r requirements.txt`
3. Ensure `.env` contains your `GROQ_API_KEY`.
4. Run the server: `python -m uvicorn backend.main:app --reload`

### 2. Frontend Setup
1. Navigate to `bookbot/frontend`.
2. Install dependencies: `npm install`
3. Run the dev server: `npm run dev`

---

## 🛡️ Core Features

- **Anti-Spoiler Protection**: Retrieval is filtered by your current page number.
- **Enthusiastic Librarian Personality**: AI persona designed for book lovers.
- **Gamified Stats**: Earn XP, level up, and unlock badges (Night Owl, Speed Reader, etc.).
- **Smart Suggestions**: Dynamic follow-up questions based on the current context.
- **Session Quotes**: Beautiful, context-aware quotes to start each reading session.
