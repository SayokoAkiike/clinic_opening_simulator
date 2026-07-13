from fastapi import FastAPI

app = FastAPI(title="Clinic Opening Simulator API")

@app.get("/health")
def health():
    return {"status": "ok"}
