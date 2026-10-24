# Verified authentication project

The delivered scope is customer and staff login/registration, password recovery by email code, and a draft Terms and Conditions page. There is no pharmacy dashboard, product catalogue, checkout, or prescription workflow.

## Checks performed

- Django 5.2.17 system check: no issues.
- Migration consistency check: no changes required after migration `0002`; the migration was applied to the local development database after backing it up.
- 28 automated authentication/security tests passed. These include hashed passwords, email uniqueness, input validation, CSRF, POST-only logout, customer/staff separation, staff approval, login throttling, protected demo seeding, terms acceptance, and password recovery code expiry, attempt limit and reuse prevention.
- Browser checked the login, registration, recovery, and terms pages. The Terms Back button returned to registration.
- Registration, recovery and terms layouts checked at desktop size and 390-pixel mobile width: no horizontal scrolling.

A successful login shows a signed-in confirmation on the login page because only authentication screens are included. Staff registrations require administrator approval. The Figma demo customer is created only by the optional seed_demo command. In local development, reset emails print to the server terminal; real delivery needs SMTP configuration. The terms text is a draft and needs project approval before deployment.

## Design references

- Customer register: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=187-675
- Customer login: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=49-76
- Staff login: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=187-559
- Staff register: https://www.figma.com/design/Iln0hUDEeDOBDozXc1PwdZ/UI-UX-System-Specification-Pharmacy-System?node-id=163-233

Native Figma frames: customer register 502 x 624; staff register 519 x 651; login 1285 x 900. Layout adapts to smaller screens. Images and vectors are stored locally in frontend/static/accounts/assets. Poppins, Sacramento and Kavivanar are stored locally with their font licence notices.

The ZIP excludes virtual environments, personal accounts, database files, temporary verification files and development secrets. First startup creates your own local database.
