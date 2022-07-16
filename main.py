from fastapi import FastAPI, Response, status

app = FastAPI()


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

    response.status_code = status.HTTP_403_FORBIDDEN
    return {"status": "not authorized"}
