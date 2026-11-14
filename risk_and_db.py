from datetime import datetime
import json
import sqlite3

DB_NAME = "news_quant_memory.db"


# ==========================================
# 1. DATABASE EVALUASI HISTORIS (SQLITE)
# ==========================================
def init_db():
  """Membuat tabel predictions_log jika belum ada."""
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_name TEXT NOT NULL,
            consensus_forecast TEXT,
            previous_actual TEXT,
            predicted_surprise TEXT,
            action_signal TEXT,
            confidence_score INTEGER,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            raw_json TEXT,
            actual_released TEXT DEFAULT 'PENDING',
            market_sensitivity_note TEXT DEFAULT 'Menunggu rilis aktual'
        )
    """)
  conn.commit()
  conn.close()


def save_prediction_to_db(
    event_name: str, forecast: str, previous: str, prediction_json_str: str
) -> int:
  """Menyimpan hasil JSON prediksi AI ke SQLite dan mengembalikan ID baris."""
  init_db()
  data = json.loads(prediction_json_str)
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT INTO predictions_log (
            timestamp, event_name, consensus_forecast, previous_actual,
            predicted_surprise, action_signal, confidence_score,
            entry_price, stop_loss, take_profit, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
      (
          datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
          event_name,
          forecast,
          previous,
          data.get("predicted_data_surprise"),
          data.get("action_signal"),
          data.get("confidence_score"),
          data.get("entry_price"),
          data.get("stop_loss"),
          data.get("take_profit"),
          prediction_json_str,
      ),
  )
  row_id = cursor.lastrowid
  conn.commit()
  conn.close()
  return row_id


def update_actual_release(
    record_id: int, actual_released: str, sensitivity_note: str
):
  """Dipanggil setelah berita rilis untuk mencatat angka Actual & reaksi pasar."""
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute(
      """
        UPDATE predictions_log
        SET actual_released = ?, market_sensitivity_note = ?
        WHERE id = ?
    """,
      (actual_released, sensitivity_note, record_id),
  )
  conn.commit()
  conn.close()


def get_last_3_evaluations() -> str:
  """Memuat 3 baris terakhir dari SQLite untuk dimasukkan ke dalam prompt AI."""
  init_db()
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute("""
        SELECT timestamp, event_name, consensus_forecast, predicted_surprise,
               action_signal, confidence_score, actual_released, market_sensitivity_note
        FROM predictions_log
        ORDER BY id DESC
        LIMIT 3
    """)
  rows = cursor.fetchall()
  conn.close()

  if not rows:
    return (
        "Belum ada riwayat evaluasi di database (ini adalah eksekusi pertama)."
    )

  history_lines = []
  for r in rows:
    history_lines.append(
        f"- [{r[0]}] Event: {r[1]} | Forecast: {r[2]} | Prediksi AI: {r[3]}"
        f" ({r[4]}, Conf: {r[5]}%) | Actual Rilis: {r[6]} | Reaksi Pasar:"
        f" {r[7]}"
    )
  return "\n".join(history_lines)


# ==========================================
# 2. CONFIDENCE GATE & SPREAD FILTER
# ==========================================
def evaluate_execution_gate(
    prediction_json_str: str,
    current_spread_points: float,
    max_spread_points: float = 30.0,
) -> dict:
  """
    Menerapkan aturan ambang batas sebelum eksekusi order:
    1. Confidence score wajib >= 80 dan action_signal != 'WAIT'.
    2. Jika spread broker > 30 poin (XAUUSD), tunda market order dan alihkan ke POST_NEWS_BREAKOUT (tunggu close candle M5 pertama).
    """
  data = json.loads(prediction_json_str)
  confidence = int(data.get("confidence_score", 0))
  signal = data.get("action_signal", "WAIT")

  # Gate 1: Cek Confidence Score & Sinyal
  if signal == "WAIT" or confidence < 80:
    return {
        "execution_status": "BLOCKED_LOW_CONFIDENCE",
        "final_order_mode": "NO_TRADE",
        "reason": (
            f"Confidence score ({confidence}%) di bawah ambang batas 80% atau"
            f" sinyal adalah {signal}."
        ),
    }

  # Gate 2: Cek Spread Broker (Contoh XAUUSD max 30 poin / 3 pips)
  if current_spread_points > max_spread_points:
    return {
        "execution_status": "DELAYED_HIGH_SPREAD",
        "final_order_mode": "POST_NEWS_BREAKOUT_M5",
        "direction": (
            "BUY_BREAKOUT" if "BUY" in signal else "SELL_BREAKOUT"
        ),
        "reason": (
            f"Spread broker saat ini ({current_spread_points} poin) melebihi"
            f" batas normal ({max_spread_points} poin). Market order Pre-News"
            " dibatalkan untuk menghindari slippage ekstrem. Tunggu penutupan"
            " candle M5 pertama setelah rilis untuk entry breakout."
        ),
    }

  # Lolos semua filter: Eksekusi Pre-News (3-5 menit sebelum rilis)
  return {
      "execution_status": "APPROVED_PRE_NEWS",
      "final_order_mode": "EXECUTE_3_TO_5_MINS_BEFORE_RELEASE",
      "direction": signal,
      "entry_price": data.get("entry_price"),
      "stop_loss": data.get("stop_loss"),
      "take_profit": data.get("take_profit"),
      "reason": (
          f"Confidence ({confidence}%) >= 80 dan spread normal"
          f" ({current_spread_points} <= {max_spread_points} poin). Siap"
          " eksekusi Pre-News."
      ),
  }