import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("OIDC_ISSUER", "https://issuer.test/realms/vantor")
os.environ.setdefault("JWT_AUDIENCE", "vantor-web")
