# BookBot — Context-Aware Reading Assistant

BookBot is an immersive, gamified reading assistant that reads your books and discusses them with you — without ever spoiling future chapters. It's a Retrieval-Augmented Generation (RAG) application that uses a vector database to provide context-aware answers to your questions about the book you're reading.

## ✨ Features in Detail

-   **Anti-Spoiler Protection**: BookBot is aware of your current page number and will only use content from the pages you've already read to answer your questions.
-   **Enthusiastic Librarian Personality**: The AI persona is designed to be a friendly and enthusiastic book lover, making your reading experience more enjoyable.
-   **Gamified Stats**: Earn XP, level up, and unlock badges for your reading achievements (e.g., Night Owl, Speed Reader).
-   **Smart Suggestions**: Get dynamic follow-up questions based on the current context to help you delve deeper into the book.
-   **Session Quotes**: Start each reading session with beautiful, context-aware quotes from the book.
-   **PDF and Text Ingestion**: Ingest books in either PDF or plain text format.

## ⚙️ How It Works

BookBot uses a Retrieval-Augmented Generation (RAG) architecture. Here's a high-level overview of the process:

1.  **Ingestion**: A book (PDF or text) is uploaded. The content is chunked into individual pages.
2.  **Embedding**: The content of each page is converted into a vector embedding using a sentence transformer model.
3.  **Storage**: The embeddings and the corresponding page content are stored in a ChromaDB vector database.
4.  **Retrieval**: When you ask a question, the question is converted into an embedding. A similarity search is performed against the vector database to find the most relevant pages (chunks) from the book, filtered by your current page number to prevent spoilers.
5.  **Generation**: The retrieved page content is then passed to a Large Language Model (LLM) along with your question and a prompt to generate a context-aware answer.

## 🛠️ Tech Stack

### Backend

-   **Python**: The core programming language.
-   **FastAPI**: A modern, fast (high-performance) web framework for building APIs.
-   **ChromaDB**: An open-source embedding database for building AI-powered applications.
-   **Groq**: The Large Language Model (LLM) for generating answers.
-   **Sentence-Transformers**: A Python framework for state-of-the-art sentence, text and image embeddings.
-   **Uvicorn**: An ASGI server for running the FastAPI application.
-   **Pydantic**: Data validation and settings management using Python type annotations.

### Frontend

-   **React**: A JavaScript library for building user interfaces.
-   **Vite**: A fast frontend build tool.
-   **Tailwind CSS**: A utility-first CSS framework for rapid UI development.
-   **canvas-confetti**: For some fun UI effects!

## 🚀 Getting Started

### Prerequisites

-   Python 3.8+ and `pip`
-   Node.js 14+ and `npm`
-   A Groq API key

### 1. Backend Setup

1.  **Navigate to the `bookbot` directory:**
    ```bash
    cd bookbot
    ```

2.  **Create a virtual environment and activate it:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create a `.env` file** in the `bookbot` directory by copying the `.env.example` file. Add your `GROQ_API_KEY`:
    ```
    GROQ_API_KEY="your-groq-api-key"
    ```

5.  **Run the server:**
    ```bash
    python -m uvicorn backend.main:app --reload
    ```
    The backend API will be available at `http://localhost:8000`. You can see the interactive API documentation at `http://localhost:8000/docs`.

### 2. Frontend Setup

1.  **Navigate to the `frontend` directory:**
    ```bash
    cd bookbot/frontend
    ```

2.  **Install dependencies:**
    ```bash
    npm install
    ```

3.  **Run the dev server:**
    ```bash
    npm run dev
    ```
    The frontend will be available at `http://localhost:5173`.

### 3. Ingesting a Book

To start chatting with a book, you first need to ingest it. You can do this via the web interface or by using a script. The backend exposes an endpoint to ingest PDF files.

## 📁 Project Structure

```
.
├── bookbot/
│   ├── backend/         # FastAPI backend application
│   │   ├── __init__.py
│   │   ├── embeddings.py  # Text chunking and embedding logic
│   │   ├── llm.py         # LLM interaction logic (Groq)
│   │   ├── main.py        # FastAPI app and endpoints
│   │   ├── models.py      # Pydantic data models
│   │   ├── retrieval.py   # Context retrieval from ChromaDB
│   │   └── session.py     # User session management
│   ├── frontend/        # React frontend application
│   │   ├── public/
│   │   └── src/
│   │       ├── components/  # React components
│   │       ├── hooks/       # Custom React hooks
│   │       ├── App.jsx
│   │       └── main.jsx
│   ├── .env.example     # Example environment variables
│   └── requirements.txt # Python dependencies
├── chroma_data/         # ChromaDB data
├── .gitignore
└── README.md
```

## 🌐 API Endpoints

The main API endpoints are defined in `bookbot/backend/main.py`. Here are some of the key endpoints:

| Method | Endpoint                                | Description                                       |
| ------ | --------------------------------------- | ------------------------------------------------- |
| POST   | `/api/books/ingest/pdf`                 | Ingest a new book from a PDF file.                |
| POST   | `/api/chat`                             | The main chat endpoint with anti-spoiler logic.   |
| GET    | `/api/session/{user_id}/{book_id}`      | Get reading progress and stats for a user.        |
| GET    | `/api/books`                            | List all ingested books.                          |
| GET    | `/api/books/quote/{book_id}/{curr_page}`| Get a random quote from the pages read so far.    |

For more details, please refer to the OpenAPI documentation at `http://localhost:8000/docs`.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue if you have any suggestions or find a bug.

## 📄 License

This project is licensed under the MIT License.
