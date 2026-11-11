from django.db import migrations


def clear_unvalidated_organizations(apps, schema_editor):
    # Nadie validó la organización de estas cuentas y al quitar la aprobación podrán
    # entrar: sin esto, quien declaró el nombre de otra empresa vería sus datos.
    apps.get_model("users", "ShieldUser").objects.filter(is_approved=False).update(organization="")


def approve_existing_users(apps, schema_editor):
    # Al revertir, la columna vuelve con default=False: sin esto nadie podría entrar.
    apps.get_model("users", "ShieldUser").objects.update(is_approved=True)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_shielduser_mfa_enabled_shielduser_mfa_enabled_at_and_more"),
    ]

    operations = [
        migrations.RunPython(clear_unvalidated_organizations, approve_existing_users),
        migrations.RemoveField(model_name="shielduser", name="is_approved"),
    ]
