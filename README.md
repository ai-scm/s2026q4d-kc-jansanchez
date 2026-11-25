# Keycloak + Google + aplicación dummy FastAPI

La aplicación usa **OpenID Connect Authorization Code Flow**. FastAPI actúa como
cliente confidencial (BFF): el secreto y los tokens nunca se entregan al
navegador.

## Configuración del cliente en Keycloak

En el realm de la práctica crea o ajusta el cliente:

| Opción | Valor |
|---|---|
| Client ID | `dummy-backend` |
| Client authentication | `On` |
| Standard flow | `On` |
| Direct access grants | `Off` |
| Valid redirect URIs | `http://localhost:8000/auth/callback` |
| Valid post logout redirect URIs | `http://localhost:8000/*` |
| Web origins | `http://localhost:8000` |

En **Credentials**, copia el Client Secret. Crea `.env` a partir de
`.env.example` y coloca allí el realm, Client ID y secret reales. Si ya existe
`.env`, añade las variables que faltan sin eliminar las credenciales de
administración.

> El cliente de Google y el cliente `dummy-backend` son clientes distintos.
> El primero conecta Google con Keycloak; el segundo conecta FastAPI con
> Keycloak.

## Configuración de Google

En el Identity Provider `google` de Keycloak, copia el valor **Redirect URI**
y regístralo como Authorized redirect URI en Google Cloud. Con los valores por
defecto será:

```text
http://localhost:8080/realms/myrealm/broker/google/endpoint
```

Esta URI termina en Keycloak, no en FastAPI: Google devuelve la identidad a
Keycloak y luego Keycloak continúa el flujo con la aplicación.

## Ejecución

```bash
cp .env.example .env       # solo si todavía no tienes .env
docker compose up --build
```

Abrir <http://localhost:8000>. Hay dos accesos:

- **Entrar con Keycloak**: muestra la pantalla de login y sus proveedores.
- **Entrar directamente con Google**: añade `kc_idp_hint=google` y salta
  directamente al proveedor configurado con alias `google`.

Para observar el flujo, abre las herramientas de desarrollo del navegador,
activa **Preserve log** en Network e inicia sesión.

## Flujo y responsabilidades

```text
Navegador        FastAPI              Keycloak                Google
   | GET /login     |                     |                      |
   |--------------->|                     |                      |
   | 302 + state, nonce, redirect_uri     |                      |
   |<---------------|                     |                      |
   | GET /auth -------------------------->|                      |
   |                                      | redirige a Google -->|
   |                                      |<-- identidad Google  |
   |<------- 302 /auth/callback?code=... -|                      |
   | callback       |                     |                      |
   |--------------->| POST /token + code + client secret        |
   |                 |-------------------->|                      |
   |                 |<-- ID/access token -|                      |
   |<-- cookie de sesión + Hola Mundo ----|                      |
```

1. **Navegador:** sigue redirecciones y conserva únicamente una cookie de
   sesión firmada. Nunca conoce el Client Secret.
2. **FastAPI:** inicia el login, protege `state`/`nonce`, recibe el código,
   lo canjea usando su Client Secret, valida el ID token y crea la sesión.
3. **Keycloak:** es el Authorization Server. Decide cómo autenticar, enlaza la
   cuenta de Google con un usuario del realm y emite sus propios tokens.
4. **Google:** autentica la cuenta y entrega su identidad a Keycloak. No emite
   el token que consume esta aplicación.

El `code` es corto, temporal y de un solo uso. El **ID token** comunica quién
es el usuario; el **access token** sirve para autorizar llamadas a APIs. Esta
demo no guarda ninguno en la cookie: conserva solo cuatro claims de identidad.

## Dos URLs de Keycloak

- `KEYCLOAK_PUBLIC_URL=http://localhost:8080`: la usa el navegador.
- `KEYCLOAK_INTERNAL_URL=http://keycloak:8080`: la usa FastAPI dentro de la
  red de Docker.

Dentro de un contenedor, `localhost` apunta al mismo contenedor. Por eso
FastAPI no puede llamar a Keycloak mediante `localhost:8080`; debe utilizar el
nombre del servicio `keycloak`. `KC_HOSTNAME` mantiene estable el issuer
público de los tokens aunque el canje se haga por la red interna.

## Endpoints

| Endpoint | Función |
|---|---|
| `/` | Página pública o “Hola Mundo, usuario” |
| `/login` | Inicia login normal en Keycloak |
| `/login/google` | Inicia login indicando el IdP `google` |
| `/auth/callback` | Recibe el authorization code |
| `/logout` | Borra sesión local y cierra sesión en Keycloak |
| `/health` | Comprobación básica del backend |

Este montaje usa HTTP, credenciales de desarrollo y `start-dev`; no es una
configuración de producción.
