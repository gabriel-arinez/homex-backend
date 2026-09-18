from django.contrib.auth.models import Group

ADMINISTRATION = "ADMINISTRACION"
SALES = "VENTAS"
WORKSHOP = "TALLER"
ROLE_NAMES = (ADMINISTRATION, SALES, WORKSHOP)


def ensure_roles() -> None:
    for name in ROLE_NAMES:
        Group.objects.get_or_create(name=name)


def has_any_role(user, *roles: str) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name__in=roles).exists())
    )
