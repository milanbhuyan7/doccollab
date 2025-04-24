# DocCollab - Documentation Collaboration Platform

DocCollab is a real-time documentation collaboration platform that allows teams to import documentation from websites, edit collaboratively, and share with team members.

## Features

- **Website Scraping**: Import documentation from any website
- **Rich Text Editing**: Edit documentation with a powerful Tiptap editor
- **Real-time Collaboration**: Collaborate with team members in real-time
- **Team Management**: Invite team members to collaborate on documentation
- **Persistent Storage**: All data is saved to the database and persists across page reloads

## Tech Stack

- **Frontend**: Next.js, React, Tailwind CSS, Tiptap
- **Backend**: Django, Django REST Framework, Django Channels
- **Database**: PostgreSQL
- **WebSockets**: Django Channels with Redis
- **Deployment**: Docker, Docker Compose, Nginx

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Node.js (for local development)
- Python (for local development)

### Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/milanbhuyan7/doccollab.git
   cd doccollab
