🎬 CineCritic

«An AI-powered movie critic and recommendation system.»

CineCritic is an intelligent movie analysis system built using Mistral AI, LangChain, and LangGraph. It analyzes movies across story, characters, themes, cinematography, and genre while using conversational memory to understand user preferences and provide personalized movie recommendations.

The system can connect with internet sources and IMDb to retrieve accurate and up-to-date movie information.

---

✨ Features

- 🎭 Movie Analysis — Analyze story, characters, themes, and overall filmmaking.
- 🎥 Cinematography Analysis — Discuss visual style, camera work, lighting, and presentation.
- 🧠 AI Movie Critic — Generate structured critical reviews using Mistral AI.
- 💾 Memory — Remember user preferences and previous interactions.
- 🍿 Personalized Recommendations — Recommend movies based on the user's interests and conversation history.
- 🌐 Web-Connected Research — Retrieve information from internet sources.
- ⭐ IMDb Integration — Use IMDb information to improve movie-data accuracy.
- 🔗 LangChain — Manage prompts, models, tools, and application workflows.
- 🕸️ LangGraph — Build structured, stateful AI workflows.
- 📝 Prompt Templates — Maintain consistent and customizable AI responses.
- 🔍 Genre Comparison — Compare movies across genres, themes, and filmmaking styles.
- 📊 Structured Reviews — Produce organized movie reviews and analysis.

---

🧠 How It Works

                    ┌──────────────────┐
                    │     User Input   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Prompt Template │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │    LangGraph     │
                    │   AI Workflow    │
                    └───────┬───┬──────┘
                            │   │
             ┌──────────────┘   └──────────────┐
             ▼                                 ▼
    ┌──────────────────┐              ┌──────────────────┐
    │   Mistral AI     │              │ External Sources │
    │  Movie Analysis  │              │ Web / IMDb Data  │
    └────────┬─────────┘              └────────┬─────────┘
             │                                 │
             └──────────────┬──────────────────┘
                            ▼
                    ┌──────────────────┐
                    │     Memory       │
                    │ User Preferences │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Final Analysis & │
                    │ Recommendation   │
                    └──────────────────┘

---

🛠️ Tech Stack

Technology| Purpose
Python| Core application
Mistral AI| Large Language Model
LangChain| AI application framework
LangGraph| Stateful workflow orchestration
Prompt Templates| Structured AI prompting
Memory| User preference and conversation context
Web Sources| Current movie information
IMDb| Movie metadata and reference information

---

🎯 Core Capabilities

🎬 Movie Criticism

CineCritic can analyze:

- Story and plot
- Characters and development
- Themes and messages
- Genre
- Cinematography
- Direction and filmmaking
- Narrative structure
- Strengths and weaknesses

🍿 Personalized Recommendations

Instead of simply recommending popular movies, CineCritic uses conversational memory to understand preferences such as:

Favorite Genres
       ↓
Preferred Themes
       ↓
Previously Discussed Movies
       ↓
User Feedback
       ↓
Personalized Recommendations

This allows recommendations to become more relevant as the user interacts with the system.

🌐 Information Retrieval

Movie information can be retrieved from external sources to supplement the AI's knowledge and reduce reliance on static model knowledge.

---

🧩 LangGraph Workflow

The application can be organized as a stateful graph where different nodes perform specific tasks.

User Query
    │
    ▼
Movie Identification
    │
    ▼
Information Retrieval
    │
    ├──► Web Sources
    │
    └──► IMDb
    │
    ▼
Movie Analysis
    │
    ▼
Preference / Memory Check
    │
    ▼
Recommendation Engine
    │
    ▼
Final Response

LangGraph allows the workflow to maintain state between these stages and makes it easier to extend CineCritic with additional tools and agents.

---

📁 Project Structure

CineCritic/
│
├── app/
│   ├── main.py
│   ├── chains/
│   ├── graphs/
│   ├── prompts/
│   ├── memory/
│   ├── tools/
│   └── utils/
│
├── tests/
│
├── .env.example
├── requirements.txt
├── README.md
└── .gitignore

«The structure may evolve as new features and integrations are added.»

---

⚙️ Installation

1. Clone the repository

git clone https://github.com/your-username/CineCritic.git
cd CineCritic

2. Create a virtual environment

python -m venv venv

Activate it:

Windows

venv\Scripts\activate

Linux / macOS

source venv/bin/activate

3. Install dependencies

pip install -r requirements.txt

4. Configure environment variables

Create a ".env" file:

MISTRAL_API_KEY=your_mistral_api_key

Add the required API credentials for your web/IMDb integration if those services require authentication.

---

🚀 Usage

Run the application:

python app/main.py

Example interaction:

User:
I want a movie similar to Interstellar.

CineCritic:
Based on your previous preferences for science fiction,
emotional storytelling, and complex themes, here are some
movies that may match your interests...

---

🔮 Future Improvements

- 🎯 More advanced recommendation algorithms
- 🧠 Long-term user preference memory
- 🎞️ Better movie similarity analysis
- 🔎 Multiple web-source verification
- 📊 Movie comparison dashboards
- 🎥 Trailer and media integration
- 🗣️ Conversational movie discovery
- 📚 Larger movie knowledge base
- ⚡ Improved LangGraph agent workflows
- 🧪 Automated evaluation of AI-generated reviews

---

⚠️ Disclaimer

CineCritic is an AI-powered movie analysis project. AI-generated criticism and recommendations may contain inaccuracies or subjective interpretations. External movie information should be treated as reference data rather than an absolute judgment.

IMDb and other external services remain the property of their respective owners.

---

👨‍💻 Project

CineCritic is an experimental AI project exploring how LLMs, memory, retrieval, and agentic workflows can be combined to create a personalized movie-analysis system.

Built With

Mistral AI · LangChain · LangGraph · Python