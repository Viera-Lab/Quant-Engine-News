from ai_predictor import run_news_quant_ai_with_rules
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from risk_and_db import update_actual_release

app = FastAPI(title="Red Folder Quant AI API")

# Izinkan akses dari GitHub Pages (viera-lab.github.io)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictRequest(BaseModel):
  event_name: str
  forecast: str
  previous: str = "N/A"
  spread: float = 18.0
  ticker: str = "GC=F"


class ActualUpdateRequest(BaseModel):
  record_id: int
  actual_released: str
  sensitivity_note: str


@app.get("/")
def health_check():
  return {"status": "ONLINE", "engine": "Red Folder Quant AI Ready"}


@app.post("/predict")
def predict_news(req: PredictRequest):
  try:
    result = run_news_quant_ai_with_rules(
        upcoming_event=req.event_name,
        consensus_forecast=req.forecast,
        previous_actual=req.previous,
        current_spread_points=req.spread,
        ticker=req.ticker,
    )
    return result
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


@app.post("/update-actual")
def update_actual(req: ActualUpdateRequest):
  try:
    update_actual_release(
        req.record_id, req.actual_released, req.sensitivity_note
    )
    return {"status": "UPDATED", "record_id": req.record_id}
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
