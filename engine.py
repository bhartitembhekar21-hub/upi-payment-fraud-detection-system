import os
import re
import math
import time
import hashlib
import secrets
import sqlite3
import html
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    from datetime import timezone
    IST = timezone(timedelta(hours=5, minutes=30))

import numpy as np
import cv2
import qrcode
from PIL import Image

# -----------------------------------------------------------------------------
# Database Path & Initialization
# -----------------------------------------------------------------------------
DB_PATH = os.environ.get("UPI_SHIELD_DB", "upi_shield.db")

INDIAN_CITIES = {
    "Nagpur": (21.1458, 79.0882),
    "Mumbai": (19.0760, 72.8777),
    "Pune": (18.5204, 73.8567),
    "Delhi": (28.7041, 77.1025),
    "Bengaluru": (12.9716, 77.5946),
    "Chennai": (13.0827, 80.2707),
    "Kolkata": (22.5726, 88.3639),
    "Hyderabad": (17.3850, 78.4867),
    "Ahmedabad": (23.0225, 72.5714),
    "Jaipur": (26.9124, 75.7873)
}

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(force_reset=False):
    if force_reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vpa TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        persona TEXT NOT NULL,
        balance REAL NOT NULL,
        avg_spend REAL NOT NULL,
        is_merchant INTEGER DEFAULT 0
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_vpa TEXT NOT NULL,
        device_id TEXT NOT NULL,
        trusted_since TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(account_vpa, device_id)
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        utr TEXT UNIQUE NOT NULL,
        sender_vpa TEXT NOT NULL,
        receiver_vpa TEXT NOT NULL,
        amount REAL NOT NULL,
        city TEXT NOT NULL,
        device_id TEXT NOT NULL,
        status TEXT NOT NULL,
        risk_score REAL NOT NULL,
        rf_prob REAL NOT NULL,
        flags TEXT NOT NULL,
        decision_tier TEXT NOT NULL,
        latency_ms REAL NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS otps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        utr TEXT NOT NULL,
        otp_hash TEXT NOT NULL,
        attempts INTEGER DEFAULT 0,
        resends INTEGER DEFAULT 0,
        expires_at TIMESTAMP NOT NULL,
        is_active INTEGER DEFAULT 1
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS sms_inbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL,
        sender_vpa TEXT NOT NULL,
        message TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS liens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receiver_vpa TEXT UNIQUE NOT NULL,
        reason TEXT NOT NULL,
        placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS disputes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        utr TEXT UNIQUE NOT NULL,
        dossier_text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value REAL NOT NULL
    )""")

    default_settings = {
        "review_threshold": 0.35,
        "block_threshold": 0.90,
        "drain_ratio_limit": 0.65,
        "spending_spike_multiplier": 3.5,
        "impossible_speed_kmh": 300.0,
        "hold_on_single_soft_flag": 0.0
    }
    for k, v in default_settings.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    default_accounts = [
        ("student@upi", "Aarav Sharma", "🎓 College Student", 12000.0, 2000.0, 0),
        ("salaried@upi", "Pooja Verma", "💼 Salaried Employee", 65000.0, 750.0, 0),
        ("kirana@upi", "Gupta Provision Store", "🏪 Small Retailer / Kirana", 180000.0, 8500.0, 0),
        ("wholesale@upi", "Nagpur Agro Traders", "🏢 Wholesale Merchant / SME", 750000.0, 38000.0, 0),
        ("chai_point@upi", "Chai Point Counter", "Merchant", 0.0, 0.0, 1),
        ("city.mart@upi", "City Mart Retail", "Merchant", 0.0, 0.0, 1),
        ("electricity.board@upi", "State Electricity Board", "Merchant", 0.0, 0.0, 1),
        ("bigbasket@upi", "BigBasket Online", "Merchant", 0.0, 0.0, 1),
        ("claim-refund@fakebank", "Fake Refund Desk", "Scammer", 0.0, 0.0, 1)
    ]
    for acc in default_accounts:
        c.execute("""
        INSERT OR IGNORE INTO accounts (vpa, name, persona, balance, avg_spend, is_merchant)
        VALUES (?, ?, ?, ?, ?, ?)
        """, acc)

    conn.commit()
    conn.close()

# -----------------------------------------------------------------------------
# Math, Geolocation & Velocity Helpers
# -----------------------------------------------------------------------------
def haversine_distance(city1, city2):
    if city1 == city2 or city1 not in INDIAN_CITIES or city2 not in INDIAN_CITIES:
        return 0.0
    lat1, lon1 = INDIAN_CITIES[city1]
    lat2, lon2 = INDIAN_CITIES[city2]
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_now_ist():
    return datetime.now(IST)

def generate_utr():
    t_part = int(time.time() * 1000) % 10000000000
    r_part = secrets.randbelow(90) + 10
    return f"{t_part}{r_part}"

# -----------------------------------------------------------------------------
# QR Code Parsing, Generation & Validation
# -----------------------------------------------------------------------------
def generate_upi_qr(receiver_vpa, payee_name, amount):
    clean_vpa = receiver_vpa.strip()
    clean_name = payee_name.strip()
    link = f"upi://pay?pa={clean_vpa}&pn={clean_name}&am={amount:.2f}&cu=INR"
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img, link

def decode_qr_image(image_bytes):
    try:
        np_arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            return None, "Failed to decode image data."
        
        detector = cv2.QRCodeDetector()
        
        # 1. Direct detection
        data, _, _ = detector.detectAndDecode(img)
        if data:
            return data, None
        
        # 2. Grayscale fallback
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        data, _, _ = detector.detectAndDecode(gray)
        if data:
            return data, None
        
        # 3. 2x upscale + Thresholding fallback
        upscaled = cv2.resize(gray, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        _, thresh = cv2.threshold(upscaled, 127, 255, cv2.THRESH_BINARY)
        data, _, _ = detector.detectAndDecode(thresh)
        if data:
            return data, None

        return None, "No readable QR code found in the image."
    except Exception as e:
        return None, f"QR decoding error: {str(e)}"

def parse_upi_uri(uri_str):
    try:
        parsed = urlparse(uri_str.strip())
        if parsed.scheme.lower() != "upi" or parsed.netloc.lower() != "pay":
            return False, {}, "Invalid protocol: Must begin with 'upi://pay'."
        
        params = parse_qs(parsed.query)
        vpa = params.get("pa", [None])[0]
        pn = params.get("pn", ["Merchant"])[0]
        am_str = params.get("am", [None])[0]
        cu = params.get("cu", ["INR"])[0]

        if not vpa or "@" not in vpa:
            return False, {}, "Invalid or missing Payee VPA address ('pa')."
        
        if cu.upper() != "INR":
            return False, {}, f"Unsupported currency '{cu}'. Only 'INR' is accepted."
        
        amount = 0.0
        if am_str:
            try:
                amount = float(am_str)
                if amount <= 0:
                    return False, {}, "Transaction amount must be strictly greater than zero."
            except ValueError:
                return False, {}, "Malformed numeric amount specified in QR."

        return True, {"receiver_vpa": vpa, "payee_name": pn, "amount": amount}, None
    except Exception as e:
        return False, {}, f"URI parse failure: {str(e)}"

# -----------------------------------------------------------------------------
# Pure Investigation Engine
# -----------------------------------------------------------------------------
def get_settings():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings")
    s = {row["key"]: row["value"] for row in c.fetchall()}
    conn.close()
    return s

def investigate(
    amount, sender_vpa, receiver_vpa, city, device_id,
    active_call=False, external_link=False, model=None, scaler=None
):
    t_start = time.perf_counter()
    now = get_now_ist()
    hour_24 = now.hour
    cfg = get_settings()

    conn = get_db_connection()
    c = conn.cursor()

    # 1. Fetch Sender Account
    c.execute("SELECT * FROM accounts WHERE vpa = ?", (sender_vpa,))
    sender = c.fetchone()
    if not sender:
        conn.close()
        t_lat = round((time.perf_counter() - t_start) * 1000, 2)
        return {
            "tier": "DECLINED", "status": "UNKNOWN ACCOUNT", "score": 1.0, "rf_prob": 1.0,
            "reason": "Originating account not registered.", "log": [("Account Existence", "Sender not in system", "ALERT")],
            "flags": ["INVALID_SENDER"], "latency_ms": t_lat, "metrics": {}
        }

    balance = float(sender["balance"])
    avg_spend = float(sender["avg_spend"])

    # Compute Reserved Balance (from PENDING_OTP transactions)
    c.execute("SELECT SUM(amount) as reserved FROM transactions WHERE sender_vpa = ? AND status = 'PENDING_OTP'", (sender_vpa,))
    res_row = c.fetchone()
    reserved_funds = float(res_row["reserved"]) if res_row and res_row["reserved"] else 0.0
    avail_balance = balance - reserved_funds

    # 2. Check Device Registration
    c.execute("SELECT COUNT(*) as d_cnt FROM devices WHERE account_vpa = ?", (sender_vpa,))
    total_devs = c.fetchone()["d_cnt"]
    c.execute("SELECT * FROM devices WHERE account_vpa = ? AND device_id = ?", (sender_vpa, device_id))
    dev_match = c.fetchone()

    is_new_device = False
    if total_devs == 0:
        # Auto-enroll first device ever used
        c.execute("INSERT OR IGNORE INTO devices (account_vpa, device_id) VALUES (?, ?)", (sender_vpa, device_id))
        conn.commit()
    elif not dev_match:
        is_new_device = True

    # 3. Check Prior Success / Contact Trust Level
    c.execute("SELECT COUNT(*) as p_cnt FROM transactions WHERE sender_vpa = ? AND receiver_vpa = ? AND status = 'SUCCESS'", (sender_vpa, receiver_vpa))
    prior_success_count = c.fetchone()["p_cnt"]
    is_new_payee = (prior_success_count == 0)

    # 4. Check Beneficiary Liens
    c.execute("SELECT * FROM liens WHERE receiver_vpa = ?", (receiver_vpa,))
    active_lien = c.fetchone()

    # 5. Last SUCCESS context for Kinematics & Velocity
    c.execute("SELECT city, timestamp FROM transactions WHERE sender_vpa = ? AND status = 'SUCCESS' ORDER BY id DESC LIMIT 1", (sender_vpa,))
    last_tx = c.fetchone()
    if last_tx:
        prev_city = last_tx["city"]
        dist_km = haversine_distance(prev_city, city)
        try:
            last_dt = datetime.fromisoformat(last_tx["timestamp"])
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=IST)
            gap_sec = max(1.0, (now - last_dt).total_seconds())
        except Exception:
            gap_sec = 3600.0
    else:
        dist_km = 0.0
        gap_sec = 86400.0

    # 6. Burst Count in last 10 minutes
    ten_mins_ago = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("SELECT COUNT(*) as b_cnt FROM transactions WHERE sender_vpa = ? AND timestamp >= ?", (sender_vpa, ten_mins_ago))
    tx_count = c.fetchone()["b_cnt"]

    conn.close()

    # Calculations
    drain_ratio = float(amount) / (balance + 1e-5)
    amount_to_avg = float(amount) / (avg_spend + 1e-5)
    hours_elapsed = max(gap_sec / 3600.0, 0.0001)
    speed_kmh = dist_km / hours_elapsed

    flags = []
    log = []

    # Deterministic Sanity Checks
    if amount <= 0:
        t_lat = round((time.perf_counter() - t_start) * 1000, 2)
        return {
            "tier": "DECLINED", "status": "INVALID AMOUNT", "score": 1.0, "rf_prob": 0.0,
            "reason": "Payment amount must be greater than zero.",
            "log": [("Sanity Inspection", "Rejected non-positive transaction value.", "ALERT")],
            "flags": ["INVALID_AMOUNT"], "latency_ms": t_lat,
            "metrics": {"drain_ratio": 0.0, "amount_to_avg": 0.0, "speed_kmh": 0.0, "dist_km": dist_km, "gap_sec": gap_sec}
        }

    if amount > avail_balance:
        t_lat = round((time.perf_counter() - t_start) * 1000, 2)
        log.append(("Liquidity Check", f"Declined: Requested INR {amount:,.2f} exceeds available INR {avail_balance:,.2f}", "ALERT"))
        return {
            "tier": "DECLINED", "status": "INSUFFICIENT FUNDS", "score": 1.0, "rf_prob": 0.0,
            "reason": f"Insufficient available funds (INR {avail_balance:,.2f} available after pending reservations).",
            "log": log, "flags": ["OVERDRAW"], "latency_ms": t_lat,
            "metrics": {"drain_ratio": drain_ratio, "amount_to_avg": amount_to_avg, "speed_kmh": speed_kmh, "dist_km": dist_km, "gap_sec": gap_sec}
        }
    else:
        log.append(("Liquidity Check", f"Verified available funds (INR {avail_balance:,.2f})", "OK"))

    # Active Regulatory Lien
    if active_lien:
        flags.append("LIENED_BENEFICIARY")
        log.append(("Beneficiary Regulatory Lien", f"Beneficiary VPA flagged with active legal lien: {active_lien['reason']}", "ALERT"))
    else:
        log.append(("Beneficiary Regulatory Lien", "No active legal lien filed against beneficiary.", "OK"))

    # Scam Keywords
    scam_regex = r"(refund|cashback|lottery|winner|kyc|support|verification|helpline|reward|prize)"
    if re.search(scam_regex, receiver_vpa.lower()):
        flags.append("SUSPICIOUS_VPA")
        log.append(("VPA Scam Hygiene", f"Keyword matching malicious pattern detected in '{receiver_vpa}'", "ALERT"))
    else:
        log.append(("VPA Scam Hygiene", "Beneficiary VPA string matches trusted merchant syntax.", "OK"))

    # Kinematics
    if speed_kmh > cfg["impossible_speed_kmh"] and dist_km > 20.0:
        flags.append("IMPOSSIBLE_SPEED")
        log.append(("Kinematic Velocity", f"Physically impossible movement: {speed_kmh:,.0f} km/h across {dist_km:.1f} km.", "ALERT"))
    else:
        log.append(("Kinematic Velocity", f"{speed_kmh:,.0f} km/h transit velocity within physical boundary.", "OK"))

    # Liquidity Drain
    if drain_ratio > cfg["drain_ratio_limit"]:
        flags.append("HIGH_DRAIN")
        log.append(("Liquidity Drain", f"Elevated capital drain ({drain_ratio*100:.1f}% of total ledger).", "ALERT"))
    else:
        log.append(("Liquidity Drain", f"{drain_ratio*100:.1f}% balance drain within safety bounds.", "OK"))

    # Spending Spike
    if amount_to_avg > cfg["spending_spike_multiplier"]:
        flags.append("SPENDING_SPIKE")
        log.append(("Behavioral Baseline", f"Surge of {amount_to_avg:.1f}x over habitual daily spend.", "ALERT"))
    else:
        log.append(("Behavioral Baseline", f"{amount_to_avg:.1f}x habitual baseline is nominal.", "OK"))

    # Device Recognition
    if is_new_device:
        flags.append("NEW_DEVICE")
        log.append(("Device Token", "Unrecognized device identifier for this account.", "ALERT"))
    else:
        log.append(("Device Token", "Recognized trusted user hardware token.", "OK"))

    # Off-Hours
    if hour_24 in [23, 0, 1, 2, 3, 4]:
        flags.append("OFF_HOURS")
        log.append(("Temporal Window", f"Off-hours transaction recorded at {hour_24:02d}:00 hrs IST.", "ALERT"))
    else:
        log.append(("Temporal Window", f"Standard business operational window ({hour_24:02d}:00 hrs IST).", "OK"))

    # New Payee
    if is_new_payee:
        flags.append("NEW_PAYEE")
        log.append(("Beneficiary History", "First transfer to this payee from this account.", "ALERT"))
    else:
        log.append(("Beneficiary History", f"Verified payee with {prior_success_count} previous settled transaction(s).", "OK"))

    # Burst Activity
    if tx_count >= 5:
        flags.append("BURST")
        log.append(("Velocity Burst", f"Rapid frequency burst ({tx_count} payments in 10 minutes).", "ALERT"))

    # Declared Environmental Risks
    if active_call:
        flags.append("ACTIVE_CALL")
        log.append(("Environmental Sensor", "Concurrent unknown call active during transfer (Digital Arrest risk).", "ALERT"))
    if external_link:
        flags.append("EXTERNAL_LINK")
        log.append(("Environmental Sensor", "Transaction initiated from external SMS/messaging link.", "ALERT"))

    # Machine Learning Inference (Random Forest)
    rf_prob = 0.0
    if model is not None and scaler is not None:
        try:
            n_in = getattr(scaler, "n_features_in_", 8)
            if n_in == 8:
                feats = np.array([[amount, amount_to_avg, drain_ratio, hour_24, tx_count, 1 if is_new_device else 0, speed_kmh, gap_sec]])
            else:
                feats = np.array([[amount, amount_to_avg, drain_ratio, hour_24, tx_count, 1 if is_new_device else 0, dist_km, speed_kmh, gap_sec]])
            scaled = scaler.transform(feats)
            rf_prob = float(model.predict_proba(scaled)[0][1])
            log.append(("Random Forest Classifier", f"Computed probabilistic fraud score: {rf_prob*100:.1f}%", "OK"))
        except Exception as ex:
            log.append(("Random Forest Classifier", f"Model scoring failed: {str(ex)}. Relying strictly on rules.", "ALERT"))
            rf_prob = 0.0
    else:
        log.append(("Random Forest Classifier", "Artifacts absent; evaluation completed via rules-only gateway.", "OK"))

    # Composite Risk Computation
    hard_flags = {"SUSPICIOUS_VPA", "IMPOSSIBLE_SPEED", "LIENED_BENEFICIARY"}
    soft_flags = {"OFF_HOURS", "NEW_PAYEE"}
    
    if any(hf in flags for hf in hard_flags):
        score = 0.99
    elif "HIGH_DRAIN" in flags and "NEW_DEVICE" in flags:
        score = 0.96
    elif len(flags) >= 3:
        score = max(rf_prob, 0.78)
    elif len(flags) == 1 and list(flags)[0] in soft_flags and not bool(cfg["hold_on_single_soft_flag"]):
        # Soft flag alone stays below review threshold
        score = min(max(rf_prob, 0.08), cfg["review_threshold"] - 0.05)
    elif len(flags) >= 1:
        score = max(rf_prob, 0.52)
    else:
        score = min(max(rf_prob, 0.05), 0.18)

    # 3-Tier Policy
    if score >= cfg["block_threshold"]:
        tier = "BLOCKED"
        status = "CRITICAL RISK: PAYMENT BLOCKED"
        reason = f"Payment terminated at switch due to multi-vector anomaly triggers: ({', '.join(flags)})."
    elif score >= cfg["review_threshold"]:
        tier = "PENDING_OTP"
        status = "SUSPICIOUS PAYMENT: PRE-DEBIT OTP HOLD"
        reason = f"Payment held under pre-debit freeze pending step-up OTP challenge. Triggers: ({', '.join(flags)})."
    else:
        tier = "CLEARED"
        status = "CLEARED FOR SETTLEMENT"
        reason = "All security telemetry and behavioral checks cleared safely."

    t_lat = round((time.perf_counter() - t_start) * 1000, 2)
    return {
        "tier": tier,
        "status": status,
        "score": score,
        "rf_prob": rf_prob,
        "reason": reason,
        "flags": flags,
        "log": log,
        "latency_ms": t_lat,
        "metrics": {
            "drain_ratio": drain_ratio,
            "amount_to_avg": amount_to_avg,
            "speed_kmh": speed_kmh,
            "dist_km": dist_km,
            "gap_sec": gap_sec
        }
    }

# -----------------------------------------------------------------------------
# Transaction Ledger Operations (State Transitions)
# -----------------------------------------------------------------------------
def record_transaction(sender_vpa, receiver_vpa, amount, city, device_id, inv_result):
    conn = get_db_connection()
    c = conn.cursor()
    utr = generate_utr()
    tier = inv_result["tier"]
    status = "SUCCESS" if tier == "CLEARED" else ("PENDING_OTP" if tier == "PENDING_OTP" else "BLOCKED")

    c.execute("""
    INSERT INTO transactions (
        utr, sender_vpa, receiver_vpa, amount, city, device_id, status,
        risk_score, rf_prob, flags, decision_tier, latency_ms
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        utr, sender_vpa, receiver_vpa, amount, city, device_id, status,
        inv_result["score"], inv_result["rf_prob"], ",".join(inv_result["flags"]),
        tier, inv_result["latency_ms"]
    ))

    # Debit balance immediately ONLY if cleared
    if status == "SUCCESS":
        c.execute("UPDATE accounts SET balance = balance - ? WHERE vpa = ?", (amount, sender_vpa))
        c.execute("UPDATE accounts SET balance = balance + ? WHERE vpa = ?", (amount, receiver_vpa))

    conn.commit()
    conn.close()
    return utr, status

def create_otp_challenge(utr, device_id, sender_vpa):
    otp = f"{secrets.randbelow(9000) + 1000}"
    otp_hash = hashlib.sha256(otp.encode("utf-8")).hexdigest()
    expires_at = (get_now_ist() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE otps SET is_active = 0 WHERE utr = ?", (utr,))
    c.execute("INSERT INTO otps (utr, otp_hash, expires_at) VALUES (?, ?, ?)", (utr, otp_hash, expires_at))
    
    # Write to simulated phone SMS inbox
    msg = f"UPI Shield Security Alert: Your pre-debit verification OTP is {otp}. Valid for 5 minutes. Do not share with callers."
    c.execute("INSERT INTO sms_inbox (device_id, sender_vpa, message) VALUES (?, ?, ?)", (device_id, sender_vpa, msg))
    
    conn.commit()
    conn.close()
    return otp

def verify_otp_challenge(utr, entered_otp):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM otps WHERE utr = ? AND is_active = 1", (utr,))
    rec = c.fetchone()
    if not rec:
        conn.close()
        return False, "No active security challenge found for this transaction."

    # Expiry Check
    exp_dt = datetime.fromisoformat(rec["expires_at"]).replace(tzinfo=IST)
    if get_now_ist() > exp_dt:
        c.execute("UPDATE otps SET is_active = 0 WHERE id = ?", (rec["id"],))
        c.execute("UPDATE transactions SET status = 'EXPIRED' WHERE utr = ?", (utr,))
        conn.commit()
        conn.close()
        return False, "OTP has expired. Pre-debit transaction cancelled."

    entered_hash = hashlib.sha256(entered_otp.strip().encode("utf-8")).hexdigest()
    if entered_hash == rec["otp_hash"]:
        # Cleared: Complete transaction and update ledger
        c.execute("UPDATE otps SET is_active = 0 WHERE id = ?", (rec["id"],))
        c.execute("SELECT sender_vpa, receiver_vpa, amount FROM transactions WHERE utr = ?", (utr,))
        tx = c.fetchone()
        if tx:
            c.execute("UPDATE transactions SET status = 'SUCCESS' WHERE utr = ?", (utr,))
            c.execute("UPDATE accounts SET balance = balance - ? WHERE vpa = ?", (tx["amount"], tx["sender_vpa"]))
            c.execute("UPDATE accounts SET balance = balance + ? WHERE vpa = ?", (tx["amount"], tx["receiver_vpa"]))
        conn.commit()
        conn.close()
        return True, "OTP verified successfully. Funds debited and cleared for settlement."
    else:
        attempts = rec["attempts"] + 1
        if attempts >= 3:
            c.execute("UPDATE otps SET is_active = 0, attempts = ? WHERE id = ?", (attempts, rec["id"]))
            c.execute("UPDATE transactions SET status = 'BLOCKED' WHERE utr = ?", (utr,))
            conn.commit()
            conn.close()
            return False, "Three incorrect attempts. Transaction blocked for security."
        else:
            c.execute("UPDATE otps SET attempts = ? WHERE id = ?", (attempts, rec["id"]))
            conn.commit()
            conn.close()
            return False, f"Incorrect OTP. {3 - attempts} attempt(s) remaining."

def resend_otp_challenge(utr, device_id, sender_vpa):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM otps WHERE utr = ? AND is_active = 1", (utr,))
    rec = c.fetchone()
    if not rec:
        conn.close()
        return False, "No active challenge to resend."
    if rec["resends"] >= 3:
        conn.close()
        return False, "Maximum resend limit (3) exceeded."
    
    otp = f"{secrets.randbelow(9000) + 1000}"
    otp_hash = hashlib.sha256(otp.encode("utf-8")).hexdigest()
    expires_at = (get_now_ist() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    resends = rec["resends"] + 1
    
    c.execute("UPDATE otps SET otp_hash = ?, expires_at = ?, resends = ? WHERE id = ?", (otp_hash, expires_at, resends, rec["id"]))
    msg = f"UPI Shield Security: Your renewed OTP is {otp}. Valid for 5 minutes."
    c.execute("INSERT INTO sms_inbox (device_id, sender_vpa, message) VALUES (?, ?, ?)", (device_id, sender_vpa, msg))
    conn.commit()
    conn.close()
    return True, "A new OTP has been dispatched to your SMS inbox."

# -----------------------------------------------------------------------------
# Remediation: Liens & Statutory Disputes
# -----------------------------------------------------------------------------
def place_beneficiary_lien(receiver_vpa, reason):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO liens (receiver_vpa, reason) VALUES (?, ?)", (receiver_vpa, reason))
    conn.commit()
    conn.close()

def remove_beneficiary_lien(receiver_vpa):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM liens WHERE receiver_vpa = ?", (receiver_vpa,))
    conn.commit()
    conn.close()

def generate_dispute_dossier(utr):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM transactions WHERE utr = ?", (utr,))
    tx = c.fetchone()
    if not tx:
        conn.close()
        return "Transaction not found."
    
    c.execute("SELECT * FROM disputes WHERE utr = ?", (utr,))
    existing = c.fetchone()
    if existing:
        conn.close()
        return existing["dossier_text"]

    dossier = f"""OFFICIAL ELECTRONIC FRAUD DISPUTE DOSSIER
Generated At: {get_now_ist().strftime('%Y-%m-%d %H:%M:%S %Z')}
UTR Reference: {tx['utr']}
Sender VPA: {tx['sender_vpa']}
Beneficiary VPA: {tx['receiver_vpa']}
Transaction Amount: INR {tx['amount']:,.2f}
Originating City: {tx['city']}
Terminal Device ID: {tx['device_id']}
Final Switch Status: {tx['status']}
Composite Risk: {tx['risk_score']*100:.1f}%
Random Forest Prob: {tx['rf_prob']*100:.1f}%
Flagged Risk Indicators: {tx['flags'] if tx['flags'] else 'None'}
Switch Execution Latency: {tx['latency_ms']:.2f} ms
Statutory Regulatory Authority: Reserve Bank of India (RBI)
Directive: Limiting Customer Liability in Unauthorized Electronic Banking Transactions (DBR.No.Leg.BC.78/09.07.005/2017-18).
Immediate Legal Redressal: National Cyber Crime Reporting Portal (cybercrime.gov.in) | Helpline: 1930
"""
    c.execute("INSERT INTO disputes (utr, dossier_text) VALUES (?, ?)", (utr, dossier))
    conn.commit()
    conn.close()
    return dossier
