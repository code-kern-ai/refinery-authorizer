from fastapi import FastAPI, Response, status, responses
import os
import logging
import telemetry


OTLP_GRPC_ENDPOINT = os.getenv("OTLP_GRPC_ENDPOINT", "tempo:4317")

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


@app.get("/healthcheck")
def healthcheck() -> responses.PlainTextResponse:
    return responses.PlainTextResponse("OK")
