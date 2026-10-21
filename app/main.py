from fastapi import FastAPI

app = FastAPI(title="Hangtime")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
