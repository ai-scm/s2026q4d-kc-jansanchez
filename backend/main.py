import html
import os
from urllib.parse import urlencode

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware


KEYCLOAK_PUBLIC_URL = os.getenv("KEYCLOAK_PUBLIC_URL", "http://localhost:8080").rstrip("/")
KEYCLOAK_INTERNAL_URL = os.getenv("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080").rstrip("/")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "myrealm")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "dummy-backend")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
APP_URL = os.getenv("APP_URL", "http://localhost:8000").rstrip("/")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me-in-local-env")

public_realm_url = f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}"
internal_realm_url = f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}"

app = FastAPI(title="Keycloak dummy app")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=APP_URL.startswith("https://"),
)

oauth = OAuth()
oauth.register(
    name="keycloak",
    client_id=KEYCLOAK_CLIENT_ID,
    client_secret=KEYCLOAK_CLIENT_SECRET,
    authorize_url=f"{public_realm_url}/protocol/openid-connect/auth",
    access_token_url=f"{internal_realm_url}/protocol/openid-connect/token",
    api_base_url=f"{internal_realm_url}/protocol/openid-connect/",
    # Authlib incorpora estos argumentos directamente a server_metadata.
    # La URL pública también es el issuer de los tokens.
    issuer=public_realm_url,
    end_session_endpoint=f"{public_realm_url}/protocol/openid-connect/logout",
    userinfo_endpoint=f"{internal_realm_url}/protocol/openid-connect/userinfo",
    jwks_uri=f"{internal_realm_url}/protocol/openid-connect/certs",
    client_kwargs={"scope": "openid profile email"},
)


def page(body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Keycloak Dummy</title>
    <style>
      body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 4rem auto; padding: 0 1rem; }}
      a {{ display: inline-block; margin: .35rem .5rem .35rem 0; }}
      code {{ background: #eee; padding: .15rem .3rem; }}
    </style>
  </head>
  <body>{body}</body>
</html>"""
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    user = request.session.get("user")
    if not user:
        return page(
            "<h1>Aplicación dummy</h1>"
            "<p>No has iniciado sesión.</p>"
            '<a href="/login">Entrar con Keycloak</a>'
            '<a href="/login/google">Entrar directamente con Google</a>'
        )

    name = html.escape(user.get("name") or user.get("preferred_username") or user.get("email") or "usuario")
    email = html.escape(user.get("email", "no disponible"))
    subject = html.escape(user.get("sub", "no disponible"))
    return page(
        f"<h1>Hola Mundo, {name}</h1>"
        f"<p>Email: <code>{email}</code></p>"
        f"<p>Identificador de Keycloak (<code>sub</code>): <code>{subject}</code></p>"
        '<a href="/logout">Cerrar sesión</a>'
    )


@app.get("/login")
async def login(request: Request) -> RedirectResponse:
    if not KEYCLOAK_CLIENT_SECRET:
        return RedirectResponse("/config-error", status_code=303)
    return await oauth.keycloak.authorize_redirect(
        request,
        redirect_uri=f"{APP_URL}/auth/callback",
    )


@app.get("/login/google")
async def login_with_google(request: Request) -> RedirectResponse:
    if not KEYCLOAK_CLIENT_SECRET:
        return RedirectResponse("/config-error", status_code=303)
    return await oauth.keycloak.authorize_redirect(
        request,
        redirect_uri=f"{APP_URL}/auth/callback",
        kc_idp_hint="google",
    )


@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.keycloak.authorize_access_token(request)
    except (OAuthError, RuntimeError) as exc:
        detail = html.escape(getattr(exc, "description", None) or str(exc))
        return page(f"<h1>Error de autenticación</h1><p>{detail}</p><a href='/'>Volver</a>")

    # Authlib verifica firma, issuer, audience, nonce y expiración del ID token.
    claims = token.get("userinfo", {})
    request.session.clear()
    request.session["user"] = {
        key: claims[key]
        for key in ("sub", "name", "preferred_username", "email")
        if key in claims
    }
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    query = urlencode(
        {
            "client_id": KEYCLOAK_CLIENT_ID,
            "post_logout_redirect_uri": f"{APP_URL}/",
        }
    )
    return RedirectResponse(
        f"{public_realm_url}/protocol/openid-connect/logout?{query}",
        status_code=303,
    )


@app.get("/config-error", response_class=HTMLResponse)
async def config_error() -> HTMLResponse:
    return page(
        "<h1>Falta configuración</h1>"
        "<p>Define <code>KEYCLOAK_CLIENT_SECRET</code> en el archivo <code>.env</code> "
        "y vuelve a crear el contenedor.</p>"
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
