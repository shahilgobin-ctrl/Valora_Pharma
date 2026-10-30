# About and Contact integration review

Reviewed on **30 October 2026**. Only the About/Contact contribution is changed.
Teammates' source snapshots were inspected and tested without editing them.
No teammate branch was merged or rewritten during this review.

## Result

The contribution passes its tests and the isolated runtime checks below.
**Team templates do not match exactly; the complete team application is not
cleared for merging.** Runtime compatibility does not resolve Git conflicts or
validate the final combined application.

The available module catalogue calls for a shared Git repository, individual
contribution history, a Django web project and a demonstration/video explaining
the code. This work follows the supplied page/code constraints; passing tests
does not certify every marking criterion or the group's complete deliverables.

## Revisions and runtime tests

Each combined check used the named branch's unchanged application code with the
new pages app and an external settings/URL harness. The harness registered the
app, template directory and routes. Each combined count includes 22 page tests
and one check following available internal links on both pages. Counts overlap.

| Branch | Inspected commit | Result |
| --- | --- | --- |
| `About-page` baseline | `20650be64f0302fbffc3d6fde9553a31a53ff77b` | Updated contribution: 42 tests pass |
| `main` | `af3cb266f44d3d208386bebd45d0f2332eef087f` | 43 combined tests pass |
| `pharmacy-login-register` | `cd233a97f1b5dbabf77f4ac2c51d392f4324cc19` | 81 combined tests pass |
| `shop` | `0286458f2435a54813a02963d29ecebd9659b8bc` | 44 combined tests pass |
| `Pharmacy-Manager` | `8546b8d69381cc903a397e3f743be4a806aa1a90` | 146 combined tests pass |
| `Shreeyash` | `e0519a77ca17fabcd60cb0a7083855ad108fc6c7` | 154 combined tests pass |
| `Admin` | `fc8364c6c2f07d391204fc278330e9e961964ba5` | 66 combined tests pass |
| `Home` | `45d10ed5db7a53c47eab4a8c4a78f5ae53ea87a3` | 89 original tests pass; combined app pending model/migration merge |

Shop retains an existing unordered-pagination warning; its tests pass. No
production server, external email delivery or Windows execution was tested.
Re-run checks after either branch changes.

## Template comparison

| Template | Header and typography | Exact match? |
| --- | --- | --- |
| About Figma / this About page | 76 px grey header; Poppins; 1265 px native frame | Matches frame layout/assets; browser rasterisation varies |
| Contact Figma / this Contact page | 64 px white header; Inter and Plus Jakarta Sans; 1579 px native frame | Matches Contact layout/assets; differs from About by design |
| Home branch | Sticky 64 px white header; 1200 px container; Poppins; different logo, spacing and greens | No |
| Shop branch | 76 px white header; DM Sans; different logo, spacing and colours | No |

The supplied About and Contact frames already differ. Unifying all screens
requires a team decision on a common header. This contribution preserves the
specified Figma frames and does not restyle teammates' pages.

## Navigation

| Destination | Named route | Behaviour |
| --- | --- | --- |
| About | `pages:about` | Active at `/about/` |
| Contact | `pages:contact` | Active at `/contact/` |
| Sign in / Register | `accounts:login` / `accounts:register` | Existing account flow |
| Home / brand | `home` | Activates when installed; respects Home's `/` or Manager's `/home/` |
| Products / Shop | `shop:shop` | Activates when installed, normally `/shop/` |
| Cart | `shop:cart` | Activates when installed, normally `/cart/` |

Home/Shop/Cart remain inactive on standalone About-page because those apps are
not installed. Optional reversal activates them in a combined project. Tests
cover both missing and installed routes.

These return links are owned by teammates and were **not edited**:

- Home branch, `frontend/templates/home.html`: About already uses
  `pages:about`; Contact targets the footer `#contact`. After integration, the
  owner can use `{% url 'pages:contact' %}` to reach the Contact page.
- Shop branch, `frontend/templates/shop/base.html`: About and Contact target
  `/`. After integration, the owner can use `{% url 'pages:about' %}` and
  `{% url 'pages:contact' %}`.

## Git merge findings

An isolated `git merge-tree` check used the inspected snapshots and shared main
baseline. It wrote only a temporary Git object database, never source files.
These are predicted conflicts, not completed merges or a substitute for checking
GitHub's current merge state.

| Target snapshot | Predicted conflicts with this contribution |
| --- | --- |
| main | None at inspected revision |
| pharmacy-login-register | None at inspected revision |
| shop | `backend/config/settings.py`, `backend/config/urls.py` |
| Pharmacy-Manager | Both config files |
| Shreeyash | `backend/config/settings.py` |
| Admin | `backend/config/settings.py` |
| Home | Both config files; pages app `admin.py`, `models.py`, `tests.py`, `urls.py`, `views.py`; pages templates `about.html`, `base.html` |

Home adds `HomepageProductImage` to the pages app, registers it in admin and
supplies `0001_homepage_product_images.py` depending on a Shop migration.
Contact adds `ContactMessage` and `0001_initial.py` in the same app.

Team integration must preserve **both models**, both admin registrations,
Home's view/route and both migration histories. Resolve source conflicts and
create a merge migration joining the two leaves; do not overwrite Home's model
or delete its migration. Then migrate a disposable database and run the full
merged suite and navigation checks.

Contact's view is separate in `contact_views.py`; this branch's original
`views.py` is preserved to reduce overlap. Shared settings and root URLs are
unchanged from the existing About-page baseline in this update. Integration
must retain every app and route when resolving those configuration conflicts.

## Completion boundary

The contribution is ready for review on About-page. A clean About-to-main merge
at the inspected revision would not integrate Home, Shop or staff apps, fix
their return links or make templates identical. The user's exact-template
condition across branches is not met. Full-team integration requires the design
decision and merge work above within the team's ownership boundaries.
