# Before accepting real care records

1. Select secure Python hosting with HTTPS and private persistent database storage.
2. Install from `requirements.txt` and set a strong stable `SECRET_KEY` as a host secret.
3. Set `SESSION_COOKIE_SECURE=1`, configure the trusted proxy only if applicable.
4. Initialise the database and create the first administrator using the private host console.
5. Add named assessor accounts in the Users screen; distribute passwords via an approved secure channel.
6. Enable and test encrypted off-site database backups and restoration; define retention and deletion procedures.
7. Add centrally enforced authentication throttling, MFA, secure password reset, event review and account lockout policies.
8. Assess UK GDPR obligations, UK hosting/data processing, access controls, sensitive information minimisation and service-user consent/lawful basis.
9. Test all roles, mobile forms, errors, exports, record access, and backups in a staging environment.
10. Conduct an independent security review before production with identifiable care information.

This package is a functioning implementation scaffold, not a currently hosted live service.
