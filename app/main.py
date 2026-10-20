from fastapi import FastAPI

app = FastAPI(title="Gym Buddy")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
