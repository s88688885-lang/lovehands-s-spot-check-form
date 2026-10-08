# Administrator access and logo recovery

The original company logo is included in `static/logo.jpg` and referenced by `templates/base.html`. Upload both files, preserving their paths.

## If previous administrator credentials no longer work

No pre-set administrator password exists. This package does **not** recreate or reset administrator accounts automatically. Accounts are in the database selected by `DATABASE_PATH`, not in GitHub or the templates.

1. Confirm Render is using the same persistent `DATABASE_PATH` and database volume as the previous deployment. Do not overwrite or delete the previous database.
2. Ensure Render's `SECRET_KEY` remains unchanged (changing it logs users out but should not change password hashes).
3. Check the original application configuration and database technology. If the original website used PostgreSQL/SQLAlchemy, the SQLite app in this package is **not a drop-in database migration**. Recover the original app/database before proceeding.
4. If the database truly is new and empty, provision a new administrator through the secured Flask CLI: `flask --app app create-admin` on an environment with the correct persistent database mounted. The command prompts for username, name and password. Do not enter a password into GitHub or a public URL.
5. Render free web services do not support persistent disks. Do not store real care records on an ephemeral SQLite database. Use paid persistent storage or migrate to managed PostgreSQL with a tested migration plan.

For troubleshooting, do **not** send passwords, `SECRET_KEY`, or database connection URLs in screenshots.
