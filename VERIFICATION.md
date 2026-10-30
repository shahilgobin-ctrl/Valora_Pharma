# Verified authentication project

The integrated scope is one login for customers, employees, suppliers, and administrators; protected customer, employee, and supplier landing pages; the Super Admin portal; direct public customer registration with a calendar date picker and unique username; superuser-managed privileged accounts; shared password recovery; and draft Terms and Conditions.

## Checks performed

- Django 5.2.17 system check: no issues; `makemigrations --check --dry-run`: no missing migration.
- 79 account and Super Admin tests passed after integration. They include shared-login routing of administrators to `/superadmin/`, account provisioning and role assignment, portal access control, audit behavior, authentication, password recovery, and registration flows.
- A disposable database was migrated from `accounts.0002` to `accounts.0003`; an existing superuser with the former staff role became an administrator.
- Migration `accounts.0004` adds optional usernames for existing accounts and requires them on new public customer signups. Migration `accounts.0005` removes customer email verification and activates earlier pending customer signups.
- Authentication templates compiled during tests. Browser layouts were checked at 1280 x 720 for registration, 1024 x 768 through 1920 x 1080 for login, and 390 x 844 for mobile. A shorter 1024 x 600 window scrolls vertically without clipping. Real SMTP delivery for password recovery has not been checked.

After sign-in, destinations come from `PHARMACY_ROLE_HOME_ROUTES`; administrators are routed to the integrated `/superadmin/` portal. Customer, employee, and supplier landing pages remain protected placeholders until their corresponding pages are integrated. New public customers can sign in immediately. Superusers create employees and suppliers inactive, then explicitly approve them. The optional demo command prints one random development password and never changes an existing account. In local development, password reset emails print to the server terminal; real delivery needs SMTP configuration. The terms text is a draft and needs project approval before deployment.

## Design references

- Customer register: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=187-675
- Customer login: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=49-76
- Earlier staff-specific login reference: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=187-559
- Staff register: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=163-233

Native Figma frames: customer register 502 x 624; staff register 519 x 651; login 1285 x 900. Layout adapts to smaller screens. Images and vectors are stored locally in frontend/static/accounts/assets. Poppins, Sacramento and Kavivanar are stored locally with their font licence notices.

This local project update does not package a ZIP. Keep virtual environments, database files, local secret keys, and SMTP credentials out of any later package.
