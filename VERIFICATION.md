# Verified authentication project

The delivered scope is one login for customers and approved staff, protected temporary landing pages for each role, public customer registration, administrator-managed employee accounts, shared password recovery by email code, and a draft Terms and Conditions page. There is no integrated customer Home page, operational staff dashboard, product catalogue, checkout, or prescription workflow.

## Checks performed

- Django 5.2.17 system check: no issues.
- Migration consistency check: no changes required after migration `0002`; the migration was applied to the local development database after backing it up.
- 40 automated authentication/security tests passed. These cover hashed passwords, email uniqueness, input validation, CSRF, POST-only logout, shared sign-in for customers and approved staff, role-specific redirects and direct-page access checks, inactive-staff denial, administrator staff creation, closed public staff registration, legacy URL redirects, login throttling, protected demo seeding, terms acceptance, and password recovery code expiry, attempt limit and reuse prevention.
- Local HTTP page checks returned 200 for login, customer registration, forgot password, and terms. `/staff/register/` returned 403 for GET and POST. Anonymous requests to both role landing pages and the older `/staff/login/` URL returned a 302 redirect to `/login/`. All authentication templates compiled.
- Earlier visual checks of registration, recovery and terms at desktop size and 390-pixel mobile width found no horizontal scrolling. A fresh browser screenshot check of this change was unavailable because the local browser preview did not attach.

A successful login sends customers to `/account/customer/` and approved staff to `/account/staff/`. Both pages say that the full customer Home or employee dashboard is coming soon; they enforce the account role on every request. Both account types use the same sign-in and forgot-password pages; old `/staff/login/` links redirect to `/login/`. Employee accounts are created in the protected Django admin area; the public staff registration endpoint is closed. When the team's real pages are integrated, replace these temporary destinations and protect their views and APIs by account role. The Figma demo customer is created only by the optional seed_demo command. In local development, reset emails print to the server terminal; real delivery needs SMTP configuration. The terms text is a draft and needs project approval before deployment.

## Design references

- Customer register: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=187-675
- Customer login: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=49-76
- Earlier staff-specific login reference: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=187-559
- Staff register: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=163-233

Native Figma frames: customer register 502 x 624; staff register 519 x 651; login 1285 x 900. Layout adapts to smaller screens. Images and vectors are stored locally in frontend/static/accounts/assets. Poppins, Sacramento and Kavivanar are stored locally with their font licence notices.

The ZIP excludes virtual environments, personal accounts, database files, temporary verification files and development secrets. First startup creates your own local database.
