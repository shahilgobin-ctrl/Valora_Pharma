# Connecting the pharmacy pages

This project has one Django backend and one account table: `accounts.User`. Customer, employee, supplier, and custom administrator pages should be Django apps in this project. Do not add another user model, login form, session system, or password table.

New public customer registrations require a unique username. Older accounts and privileged accounts may have no username, so use `user.username` with an email or name fallback when displaying it. Sign-in continues to use email and password.

## Roles and destinations

| `User.account_type` | Who creates it | First destination | Access rule |
| --- | --- | --- | --- |
| `customer` | Public registration | `accounts:customer_landing` | Active customer account |
| `staff` | Superuser in Django admin, then identity check and activation | `accounts:staff_landing` | Active employee account |
| `supplier` | Superuser in Django admin, then identity check and activation | `accounts:supplier_landing` | Active supplier account |
| `admin` | `createsuperuser` | `accounts:admin_landing` | Active Django superuser with admin role |

`is_staff` is Django's permission to enter `/admin/`; it is **not** the pharmacy employee role. `/admin/` is Django's management site. `/account/admin/` is only the temporary custom administrator landing page. Ordinary employees and suppliers must not receive `is_staff` or `is_superuser`.

After adding a teammate's app to `INSTALLED_APPS`, include its URL configuration in `backend/config/urls.py`. Protect every page and action, not just the post-login redirect:

```python
from accounts.access import pharmacy_role_required
from accounts.models import User

@pharmacy_role_required(User.AccountType.SUPPLIER)
def supplier_home(request):
    ...
```

The decorator sends anonymous users to the shared `/login/` page and returns 403 for the wrong role. For JSON endpoints, use `user_has_role(request.user, User.AccountType.SUPPLIER)` and return an appropriate JSON error. Continue to check ownership of individual records such as orders and prescriptions; a role check alone does not authorize access to every record of that role.

Once an app has a named home URL, change only its entry in `PHARMACY_ROLE_HOME_ROUTES` in `backend/config/settings.py`. For example, after a `supplier:home` route exists, replace `"supplier": "accounts:supplier_landing"` with `"supplier": "supplier:home"`. Keep the placeholder for any teammate page that has not been merged. All roles continue to authenticate through `accounts:login` and recover passwords through `accounts:password_forgot`.

## Accounts and migrations

Apply migrations with `python backend/manage.py migrate` after backing up any existing SQLite database. Migration `0003` adds supplier and administrator roles. Migration `0005` removes the former customer email-code feature and activates customer signups that were waiting for a code. Existing active accounts remain active. Review legacy accounts before a real launch.

New customer accounts are active after registration and can sign in immediately. New employee and supplier accounts created in `/admin/` start inactive and require a superuser to check identity and activate them. The admin role cannot be selected through the regular add-user form; use `createsuperuser`.

## Email and local testing

Development defaults to Django's console email backend: password reset codes appear in the server terminal. To send to real inboxes, set `DJANGO_EMAIL_BACKEND`, `DJANGO_DEFAULT_FROM_EMAIL`, `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD`, and exactly one of `DJANGO_EMAIL_USE_TLS` or `DJANGO_EMAIL_USE_SSL` for the provider. `.env.example` is a reference, not an automatically loaded file. Test delivery to an address you control before inviting real users.

The login and email request limits use Django's cache. The default local-memory cache is suitable for the single-process demo. Use a shared cache when multiple server workers are deployed; otherwise each worker has separate counters.
