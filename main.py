from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import init_db
from app.routers import auth, passes, gate, rfid

app = FastAPI(
    title="DADU Gatepass System",
    description="Campus gate pass management with RBAC, rotating QR verification, and RFID vehicle passes",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

app.include_router(auth.router)
app.include_router(passes.router)
app.include_router(gate.router)
app.include_router(rfid.router)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/ui")
def frontend():
    return FileResponse("static/index.html")
