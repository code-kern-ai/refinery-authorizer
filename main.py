from fastapi import FastAPI, Response, status, responses
import os
import logging
import requests
import telemetry


OTLP_GRPC_ENDPOINT = os.getenv("OTLP_GRPC_ENDPOINT", "tempo:4317")
HYDRA_ADMIN_URL = os.getenv("HYDRA_ADMIN_URL", "http://hydra:4445")

app_name = "refinery-authorizer"
app = FastAPI(title=app_name)

if telemetry.ENABLE_TELEMETRY:
    print("WARNING:  Running telemetry.", flush=True)
    telemetry.setting_app_name(app_name)
    telemetry.setting_otlp(app, app_name=app_name, endpoint=OTLP_GRPC_ENDPOINT)
    app.add_middleware(telemetry.PrometheusMiddleware, app_name=app_name)
    app.add_route("/metrics", telemetry.metrics)

    # Filter out /metrics
    logging.getLogger("uvicorn.access").addFilter(
        lambda record: "GET /metrics" not in record.getMessage()
    )


@app.get("/health")
async def root():
    return {"alive": "true"}


@app.post("/authorize")
def authorize(body: dict, response: Response):
    if body["resource"] == "kratos:admin":
        return resolve_kratos_admin(body, response)

    response.status_code = status.HTTP_403_FORBIDDEN
    return {"status": "not authorized"}


def resolve_kratos_admin(body, response):
    subject = body["subject"]["identity"]
    if (
        subject["traits"]["email"].split("@")[1] == "kern.ai"
        and subject["verifiable_addresses"][0]["verified"]
    ):
        response.status_code = status.HTTP_200_OK
        return {"status": "authorized"}
    elif (
        # subject metadata_public can be None so we use or {} instead of get with default
        (subject.get("metadata_public") or {}).get("role") == "ADMIN"
        and subject["verifiable_addresses"][0]["verified"]
    ):
        response.status_code = status.HTTP_200_OK
        return {"status": "authorized"}

    response.status_code = status.HTTP_403_FORBIDDEN
    return {"status": "not authorized"}


# Hydra admin API proxy (for OAuth2 login/consent flows)
@app.get("/hydra/consent")
def get_consent(challenge: str | None = None):
    if not challenge:
        return responses.JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "missing challenge"},
        )
    try:
        resp = requests.get(
            f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/requests/consent",
            params={"consent_challenge": challenge},
            timeout=10,
        )
        resp.raise_for_status()
        return responses.JSONResponse(status_code=resp.status_code, content=resp.json())
    except requests.RequestException as e:
        logging.getLogger(__name__).warning("Hydra consent get failed: %s", e)
        return responses.JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "failed to get consent request"},
        )


@app.post("/hydra/consent/accept")
def accept_consent(body: dict):
    challenge = body.get("challenge")
    if not challenge:
        return responses.JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "missing challenge"},
        )
    payload = {
        k: body[k]
        for k in (
            "grant_scope",
            "grant_access_token_audience",
            "remember",
            "remember_for",
            "session",
        )
        if k in body
    }
    try:
        resp = requests.put(
            f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/requests/consent/accept",
            params={"consent_challenge": challenge},
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return responses.JSONResponse(content={"redirect_to": data.get("redirect_to", "")})
    except requests.RequestException as e:
        logging.getLogger(__name__).warning("Hydra consent accept failed: %s", e)
        return responses.JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "failed to accept consent request"},
        )


@app.post("/hydra/consent/reject")
def reject_consent(body: dict):
    challenge = body.get("challenge")
    if not challenge:
        return responses.JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "missing challenge"},
        )
    try:
        resp = requests.put(
            f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/requests/consent/reject",
            params={"consent_challenge": challenge},
            json={
                "error": "access_denied",
                "error_description": "The resource owner denied the request",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return responses.JSONResponse(content={"redirect_to": data.get("redirect_to", "")})
    except requests.RequestException as e:
        logging.getLogger(__name__).warning("Hydra consent reject failed: %s", e)
        return responses.JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "failed to reject consent request"},
        )


@app.post("/hydra/login/accept")
def accept_login(body: dict):
    challenge = body.get("challenge")
    subject = body.get("subject")
    if not challenge or not subject:
        return responses.JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "missing challenge or subject"},
        )
    try:
        resp = requests.put(
            f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/requests/login/accept",
            params={"login_challenge": challenge},
            json={"subject": subject, "remember": True, "remember_for": 3600},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return responses.JSONResponse(content={"redirect_to": data.get("redirect_to", "")})
    except requests.RequestException as e:
        logging.getLogger(__name__).warning("Hydra login accept failed: %s", e)
        return responses.JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "An error occurred while accepting the login challenge"},
        )


@app.get("/healthcheck")
def healthcheck() -> responses.PlainTextResponse:
    return responses.PlainTextResponse("OK")
