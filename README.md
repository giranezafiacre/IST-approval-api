# IST Approval System

A Django-based Purchase Request and Approval System.  
This application allows users to create purchase requests, attach proforma invoices, and approve requests across multiple approval levels.

---

## Features

- User authentication and role-based access
- Create, edit, and view purchase requests
- Upload Proforma invoices and receipts
- Multi-level approval workflow
- Automatic Purchase Order generation after approvals
- Filter requests by status and search by title

---

## Tech Stack

- **Backend:** Django, Django REST Framework
- **Database:** SQLite (development) / PostgreSQL (production)
- **Frontend:** Optional React/Next.js frontend
- **Containerization:** Docker & Docker Compose

---

## Getting Started

### Prerequisites

- Python 3.11+
- pip or poetry
- Docker & Docker Compose (optional)

### Setup

1. Clone the repository:

```bash
git clone https://github.com/giranezafiacre/IST-approval-api.git
cd IST-approval-api


# Setup virtual environment and activate it
python -m venv env
env\Scripts\activate   # Windows
# source env/bin/activate  # Linux / macOS

# Install dependencies
pip install -r requirements.txt

# Apply migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
```
API docs: https://documenter.getpostman.com/view/10653379/2sB3dJyCSo 
