# Django's built-in Group model groups users by role and can hold permissions.
from django.contrib.auth.models import Group

# BaseCommand allows this file to run as a Django management command.
from django.core.management.base import BaseCommand

# Transactions ensure that the database changes succeed together.
from django.db import transaction


class Command(BaseCommand):
    # Description displayed by:
    # python manage.py help setup_roles
    help = "Create the pharmacy staff role groups."

    # If an error occurs, roll back the database changes made by this command.
    @transaction.atomic
    def handle(self, *args, **options):
        # These names must be consistent wherever we check staff roles.
        role_names = [
            "Pharmacist",
            "Pharmacy Manager",
        ]

        for role_name in role_names:
            # Retrieve the group if it exists; otherwise, create it.
            # This makes the command safe to run more than once.
            #
            # group: the retrieved or newly created Group object.
            # created: True if a new group was created, otherwise False.
            group, created = Group.objects.get_or_create(name=role_name)

            if created:
                # Display a success message for a newly created role.
                self.stdout.write(
                    self.style.SUCCESS(f"Created role: {group.name}")
                )
            else:
                # Inform the developer that the existing role was preserved.
                self.stdout.write(f"Role already exists: {group.name}")