# Quick Reminder — PostgreSQL Deployment Version

Quick Reminder is a Flask family information, document-management, and reminder application.

## Database upgrade

This version supports **PostgreSQL** through the `DATABASE_URL` environment variable. If `DATABASE_URL` is not set, the app falls back to SQLite for local testing.

On Render, `render.yaml` creates a Render Postgres database and automatically supplies its internal connection string to the web service.

Render's Blueprint wiring uses `fromDatabase`, so you do not need to copy a database password into the repository.

## Deploy without installing Python or VS Code

1. Create a GitHub repository.
2. Upload all files from this project into the repository.
3. Open Render and choose **New → Blueprint**.
4. Connect the GitHub repository.
5. Render detects `render.yaml`.
6. Review the web service and Postgres database resources.
7. Apply the Blueprint.
8. Render builds the Flask application and connects it to PostgreSQL.
9. Open the generated `.onrender.com` URL.

## Important Render note

The included Blueprint uses Render's Free Postgres plan for demonstration. Render currently states that Free Postgres databases have a 1 GB storage limit and expire 30 days after creation; upgrade the database plan for a longer-lived application.

## Local development

```powershell
py -m venv venv
.\\venv\\Scripts\\Activate.ps1
py -m pip install -r requirements.txt
py app.py
```

If `DATABASE_URL` is not configured locally, SQLite is used automatically.

To test PostgreSQL locally, set `DATABASE_URL` to a PostgreSQL connection string, for example:

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
```

## Existing data

Changing the application from SQLite to PostgreSQL does **not automatically migrate an existing SQLite database**. The PostgreSQL database starts with the application's schema and will contain new data entered after deployment.

If you already have important SQLite data, export/migrate it before switching production databases.

## Security warning

This project handles sensitive identity information. For a real public deployment, use strong authentication, authorization, HTTPS, CSRF protection, rate limiting, secure cookies, secret management, audit logging, backups, and encrypted/persistent document storage. Use dummy Aadhaar/PAN/identity documents for a college demonstration until these protections are implemented.

Also note: the database upgrade makes the structured application data persistent on PostgreSQL, but the current uploaded-document files are still stored in the app's local `uploads/` directory. A production deployment should move those files to persistent object storage (for example, S3-compatible storage) rather than relying on the web service filesystem.
