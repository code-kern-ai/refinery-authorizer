FROM kernai/refinery-parent-images:parent-image-updates-mini

WORKDIR /app

COPY requirements*.txt .

RUN pip3 install --no-cache-dir -r requirements-dev.txt

COPY / .

CMD [ "/usr/local/bin/uvicorn", "--host", "0.0.0.0", "--port", "80", "main:app", "--reload"]