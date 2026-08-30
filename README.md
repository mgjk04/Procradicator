# Procradicator

A mobile-first Progressive Web Application (PWA) that helps reduce procrastination by turning overwhelming tasks into small actionable steps, guiding them into short focus sessions, and helping them reflect on their habits over time.

## Features

* Secure credential-based registration and login, with Google Single Sign-On (SSO) support, using JSON Web Tokens (JWT) and HTTP-only cookies.


* Task dashboard with infinite scroll and manual task modifications via a nested React Hook Form with drag-and-drop subtask reordering.


* AI-Assisted Task Management that leverages a Large Language Model (Groq) to translate natural language goals into structured, manageable task roadmaps.


* Anti-procrastination Focus Sessions that track work and rest cycles, explicitly requiring users to document a reason before abandoning an active session.


* Productivity Analytics and a Recommendation Engine that utilizes Thompson sampling to analyze past session outcomes and recommend optimal work-rest intervals.


* Local-first offline storage via a PWA service worker and IndexedDB, enabling offline CRUD operations and Focus Sessions with automatic background synchronization and conflict resolution.


* Social accountability features allowing users to add friends and view a daily leaderboard comparing total focus minutes and completed subtasks.



## Tech Stack

* **Frontend Application:** React Native, Expo Web.


* **Frontend Tooling:** React Hook Form, Zod, TanStack Query, Gluestack UI.


* **Offline & PWA:** IndexedDB, Workbox.


* **Backend Framework:** Python, FastAPI, FastAPI Users.


* **Database & ORM:** SQLModel (SQLAlchemy + Pydantic).


* **AI & Integration:** Groq LLM API, Pydantic-ai.

## Architecture & API Reference

Procradicator utilizes a strict Model-View-Controller (MVC) 5-layer architecture comprising UI, Routers, Services, Repositories, and Database layers to ensure a clear separation of concerns.

### Data Synchronization Contract

Data synchronization leverages idempotent keys, HTTP `If-Match` headers, and `ETag` versioning to handle offline/online conflict resolution seamlessly.

### Core API Endpoints

* **Authentication:** `/auth/me`

* **Tasks:**
* `POST /tasks` (Create)


* `PUT /tasks/{task_id}` (Complete Replacement)


* `DELETE /tasks/{task_id}` (Deletion)




* **Focus Sessions:**
* `POST /focus` (Creation)


* `PATCH /focus/{session_id}` (Append Progress)


* `PUT /focus/{session_id}` (Conflict Resolution Replacement)


* **Analytics:** `GET /analytics/summary`
