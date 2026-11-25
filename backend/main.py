import html
import os
from urllib.parse import urlencode

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles


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
app.mount("/static", StaticFiles(directory="static"), name="static")

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


def page(body: str, title: str = "Acceso") -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="description" content="Aplicación de demostración con Keycloak y Google">
    <title>{html.escape(title)} · Keycloak Demo</title>
    <link rel="stylesheet" href="/static/styles.css">
  </head>
  <body>
    <header class="topbar">
      <a class="brand" href="/" aria-label="Inicio">
        <span class="brand-mark" aria-hidden="true">K</span>
        <span>Keycloak Demo</span>
      </a>
      <span class="status"><i></i> Entorno local</span>
    </header>
    <main class="shell">{body}</main>
    <footer>FastAPI · OpenID Connect · Authorization Code Flow</footer>
  </body>
</html>"""
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    user = request.session.get("user")
    if not user:
        return page(
            """
            <section class="login-layout">
              <div class="intro">
                <span class="eyebrow">AUTENTICACIÓN FEDERADA</span>
                <h1>Un solo acceso.<br><em>Dos formas de entrar.</em></h1>
                <p class="lead">
                  Esta aplicación delega la identidad en Keycloak. Puedes usar
                  un usuario del realm o continuar con tu cuenta de Google.
                </p>
                <div class="flow" aria-label="Flujo de autenticación">
                  <span>Navegador</span><b>→</b><span>Keycloak</span><b>→</b><span>Google</span>
                </div>
              </div>
              <div class="card login-card">
                <div class="card-heading">
                  <span class="shield" aria-hidden="true">✓</span>
                  <div>
                    <h2>Iniciar sesión</h2>
                    <p>Elige cómo quieres identificarte</p>
                  </div>
                </div>
                <div class="actions">
                  <a class="button button-primary" href="/login">
                    <span class="keycloak-icon" aria-hidden="true">K</span>
                    Continuar con Keycloak
                  </a>
                  <div class="divider"><span>o</span></div>
                  <a class="button button-google" href="/login/google">
                    <span class="google-icon" aria-hidden="true">G</span>
                    Continuar con Google
                  </a>
                </div>
                <p class="privacy">
                  Serás redirigido de forma segura. La aplicación nunca recibe
                  tu contraseña.
                </p>
              </div>
            </section>
            """,
            "Iniciar sesión",
        )

    raw_name = user.get("name") or user.get("preferred_username") or user.get("email") or "usuario"
    name = html.escape(raw_name)
    email = html.escape(user.get("email", "no disponible"))
    subject = html.escape(user.get("sub", "no disponible"))
    initial = html.escape(raw_name[:1].upper())
    return page(
        f"""
        <section class="welcome">
          <div class="success-badge"><span>✓</span> Autenticación completada</div>
          <div class="card profile-card">
            <div class="avatar" aria-hidden="true">{initial}</div>
            <p class="overline">SESIÓN ACTIVA</p>
            <h1>Hola, <em>{name}</em></h1>
            <p class="lead">Tu identidad fue validada correctamente por Keycloak.</p>
            <dl class="user-data">
              <div>
                <dt>Correo electrónico</dt>
                <dd>{email}</dd>
              </div>
              <div>
                <dt>Identificador del usuario</dt>
                <dd><code>{subject}</code></dd>
              </div>
              <div>
                <dt>Proveedor de identidad</dt>
                <dd><span class="verified-dot"></span> Keycloak / OIDC</dd>
              </div>
            </dl>
            <a class="button button-danger" href="/logout">Cerrar sesión</a>
          </div>
        </section>
        """,
        f"Hola, {raw_name}",
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
        return page(
            f"""
            <section class="message-card card">
              <span class="message-icon error">!</span>
              <p class="overline">NO SE PUDO INICIAR SESIÓN</p>
              <h1>Error de autenticación</h1>
              <p class="lead">{detail}</p>
              <a class="button button-primary" href="/">Volver al inicio</a>
            </section>
            """,
            "Error de autenticación",
        )

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
        """
        <section class="message-card card">
          <span class="message-icon warning">!</span>
          <p class="overline">CONFIGURACIÓN INCOMPLETA</p>
          <h1>Falta el Client Secret</h1>
          <p class="lead">
            Define <code>KEYCLOAK_CLIENT_SECRET</code> en el archivo
            <code>.env</code> y vuelve a crear el contenedor.
          </p>
          <a class="button button-primary" href="/">Volver al inicio</a>
        </section>
        """,
        "Falta configuración",
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
