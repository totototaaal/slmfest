from fastapi import Depends, FastAPI, Request
from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal, engine
from .kaspi import KaspiProcessor
from .security import validate_https, validate_request_origin

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Kaspi Payment API", version="1.0")


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/payment")
async def payment(request: Request, db: Session = Depends(get_db)):
    validate_https(request)
    validate_request_origin(request)
    params = {key: value for key, value in request.query_params.items()}
    processor = KaspiProcessor(db)
    response = processor.process(request, params)
    return response


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
