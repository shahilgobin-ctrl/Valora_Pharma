"""Compatibility node for the manager branch after the integrated shop history.

The metadata columns already exist in shop.0004/0005.
"""
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [("shop", "0007_merge_shop_histories")]
    operations = []
