from django.contrib.auth.hashers import Argon2PasswordHasher


class SchnellerArgon2(Argon2PasswordHasher):
    """Gleiches Verfahren (``argon2$``-Präfix), nur für Tests mit minimalem Aufwand."""

    time_cost = 1
    memory_cost = 512
    parallelism = 1
