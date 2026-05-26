ARG PARENT_IMAGE=kernai/refinery-parent-images:v2.5.0-mini

FROM ${PARENT_IMAGE} AS builder

ENV VENV_PATH=/opt/venv
ENV PATH="${VENV_PATH}/bin:${PATH}"

WORKDIR /app

USER root

RUN if [ ! -d "${VENV_PATH}" ]; then python -m venv "${VENV_PATH}"; fi

COPY requirements.txt .

RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

FROM ${PARENT_IMAGE}

ENV VENV_PATH=/opt/venv
ENV PATH="${VENV_PATH}/bin:${PATH}"

WORKDIR /app

USER root

COPY --from=builder --chown=65532:65532 ${VENV_PATH} ${VENV_PATH}
COPY --from=builder --chown=65532:65532 /app /app

USER 65532:65532

CMD ["/opt/venv/bin/uvicorn", "--host", "0.0.0.0", "--port", "80", "main:app"]
