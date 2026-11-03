from fastapi import FastAPI

app = FastAPI(
    title="FilingCite API",
    docs_url="/svc/api/docs",
    openapi_url="/svc/api/openapi.json",
)


@app.get("/svc/api/status")
def get_status():
    return {"status": "ok"}
