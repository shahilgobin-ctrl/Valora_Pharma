# Verified authentication project

The local scope is one login for customers, employees, suppliers, and administrators; protected temporary landing pages; email-verified public customer registration with a calendar date picker and unique username; superuser-managed privileged accounts; shared password recovery; and draft Terms and Conditions. The team's actual Home, employee, supplier, and custom admin pages are not yet integrated.

## Checks performed

- Django 5.2.17 system check: no issues; `makemigrations --check --dry-run`: no missing migration.
- 55 authentication/security tests passed. They cover customer verification and activation, expiry/attempt limits, resend, rollback on email failure, case-insensitive usernames, shared sign-in for four roles, role access, superuser-only account management, inactive privileged provisioning, password recovery, shared-network login and recovery limits, CSRF, and safe demo seeding.
- A disposable database was migrated from `accounts.0002` to `accounts.0003`; an existing superuser with the former staff role became an administrator.
- Migration `accounts.0004` adds optional usernames for existing accounts and requires them on new public customer signups.
- The new email templates compiled during tests. Browser layouts were checked at 1280 x 720 for registration, 1024 x 768 through 1920 x 1080 for login, and 390 x 844 for mobile. A shorter 1024 x 600 window scrolls vertically without clipping. Real SMTP delivery has not been checked.

After sign-in, the route for each role comes from `PHARMACY_ROLE_HOME_ROUTES`; the defaults are protected placeholders. Teammates can replace individual route names once their Django apps are merged. New public customers stay inactive until their email code is accepted. Superusers create employees and suppliers inactive, then explicitly approve them. The optional demo command prints one random development password and never changes an existing account. In local development, verification and reset emails print to the server terminal; real delivery needs SMTP configuration. The terms text is a draft and needs project approval before deployment.

## Design references

- Customer register: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=187-675
- Customer login: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=49-76
- Earlier staff-specific login reference: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=187-559
- Staff register: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=163-233

Native Figma frames: customer register 502 x 624; staff register 519 x 651; login 1285 x 900. Layout adapts to smaller screens. Images and vectors are stored locally in frontend/static/accounts/assets. Poppins, Sacramento and Kavivanar are stored locally with their font licence notices.

This local project update does not package a ZIP. Keep virtual environments, database files, local secret keys, and SMTP credentials out of any later package.
