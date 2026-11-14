from risk_and_db import (
    evaluate_execution_gate,
    get_last_3_evaluations,
    save_prediction_to_db,
)


def run_news_quant_ai_with_rules(
    upcoming_event: str,
    consensus_forecast: str,
    previous_actual: str,
    current_spread_points: float,
    ticker: str = "GC=F",
):
  macro_data = get_macro_comparison(months=6)
  articles_text = search_and_read_articles(upcoming_event, max_articles=4)
  tech_data = get_technical_context(ticker=ticker, interval="15m")

  # Muat 3 riwayat evaluasi terakhir dari SQLite
  past_3_runs = get_last_3_evaluations()

  client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

  prompt = f"""
    Kamu adalah Chief Macro Quant & News Trader untuk instrumen Gold (XAUUSD / GC=F).
    Analisislah event Red Folder yang akan rilis dengan menggabungkan data historis,
    pembacaan artikel penuh, struktur teknikal, dan memori evaluasi 3 rilis terakhir.

    EVENT TARGET: {upcoming_event}
    KONSENSUS FORECAST SAAT INI: {consensus_forecast}
    DATA AKTUAL BULAN LALU: {previous_actual}

    0. MEMORI EVALUASI 3 RILIS TERAKHIR (DARI DATABASE SQLITE):
    {past_3_runs}
    (Gunakan memori di atas untuk menilai apakah pasar belakangan ini lebih sensitif terhadap data inflasi CPI/PPI atau data ketenagakerjaan NFP).

    1. RIWAYAT DATA KEUANGAN, PEKERJAAN & REVISI (FRED API):
    {json.dumps(macro_data, indent=2)}

    2. KONDISI TEKNIKAL SAAT INI (M15):
    {json.dumps(tech_data, indent=2)}

    3. BACAAN ARTIKEL KOMPREHENSIF (FULL TEXT):
    {articles_text}

    ATURAN PENALARAN KUANTITATIF:
    - Berikan confidence_score >= 80 HANYA JIKA data historis FRED, narasi artikel penuh, struktur teknikal, dan sensitivitas pasar terkini saling mengonfirmasi tanpa kontradiksi.
    - Jika ragu atau terjadi konflik antara inflasi (CPI/PPI) dan pekerjaan (NFP), turunkan confidence_score di bawah 80 atau pilih WAIT.
    """

  response = client.models.generate_content(
      model="gemini-2.5-pro",
      contents=prompt,
      config=types.GenerateContentConfig(
          response_mime_type="application/json",
          response_schema=NewsTradePrediction,
          temperature=0.15,
      ),
  )

  raw_json = response.text

  # Simpan ke SQLite predictions_log
  record_id = save_prediction_to_db(
      upcoming_event, consensus_forecast, previous_actual, raw_json
  )

  # Evaluasi Confidence Gate (>=80) & Spread Filter (<=30 poin)
  gate_decision = evaluate_execution_gate(
      raw_json, current_spread_points=current_spread_points
  )

  return {
      "db_record_id": record_id,
      "ai_prediction": json.loads(raw_json),
      "execution_gate": gate_decision,
  }