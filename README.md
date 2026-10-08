# Lovehands Spot Check Website

A secure, role-based Spot Check questionnaire system for Lovehands Care Services Limited, using Flask, SQLAlchemy and PostgreSQL (SQLite for local development).

## Lovehands branding

The official Lovehands logo is included at `static/logo.png` and appears in the header on all website pages, plus the login and administrator setup screens. The website theme uses plum and green to complement the logo. When updating the brand image, replace that file while keeping its filename.

## First-time administrator login

- Username: `admin`
- Password: **You create this during setup. There is no preset password.**
- Initial setup page: `/setup`
- To prevent unauthorised registration, set the `SETUP_TOKEN` environment variable to a long secret first. Only someone who knows that token can create the initial administrator. After creating the admin account, `/setup` is disabled.

## Deploy to Render from GitHub

1. Upload the contents of this folder to a new **private GitHub repository**. Do not commit `.env` or any database files.
2. On Render choose **New > Blueprint** and select the repository. `render.yaml` configures a Python web service and PostgreSQL database. Review pricing and resources before deploying.
3. When prompted, set `SETUP_TOKEN` to a unique random value (ideally 32+ characters).
4. Render automatically supplies a generated `SECRET_KEY` and the PostgreSQL connection string. Use `COOKIE_SECURE=1` for HTTPS.
5. Open `https://YOUR-SERVICE.onrender.com/setup`, enter the setup token, your name, and choose an admin password with at least 12 characters.
6. Visit `/login`, sign in as `admin`, and add assessor accounts in **Users**.
7. Assessors log in, complete spot checks, submit, and see their own records. Admins see all submitted records in **Dashboard** and can export the summary CSV. Individual records can be printed/saved as PDF from a browser.

## Local testing

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
export SETUP_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
flask --app app run
```

Open `http://127.0.0.1:5000/setup` and use the generated setup token.

## Important security and compliance notes

- Use HTTPS, a hosted PostgreSQL database and unique passwords. SQLite is for local development and is not a durable database on Render's ephemeral filesystem.
- Confidential service-user information must not be committed to GitHub or stored in free-text GitHub issues.
- This is a functional starter application, not an independently security-audited production medical/care record system. Before operational use, set up backups, a data retention and deletion policy, an access review process, a privacy notice, appropriate UK GDPR security procedures, incident response and hosting / processor agreements. For care records, confirm where data is stored and appropriate UK GDPR safeguards.
- Automated email password resets, advanced MFA, audit event logs, role-level reporting, full CSV response export and signed-image capture are not included in this version. Admins can issue new passwords via User Management.
- First section question wording was restored as a practical default because the provided DOCX extract did not contain readable text for that section. Review those four questions against your authoritative original form before real-world use.
