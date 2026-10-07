# UPI Shield

## Run
    pip install -r requirements.txt
    streamlit run app.py

Put your trained files next to app.py:  upi_fraud_model.pkl  and  scaler.pkl
(the "(3)" names also work). Optional: upi_fraud_dataset.csv for the Training data tab.
If the model files are missing the app says so and scores with rules only.

## Files
- app.py     UI (pages, light/dark theme, checkout, QR, OTP, ledger, settings)
- engine.py  backend (SQLite ledger, fraud checks, model scoring, OTP, liens, QR, disputes)
- test_engine.py  backend tests:  python test_engine.py
- upi_shield.db   created on first run (all state lives here; reset it from Settings)
