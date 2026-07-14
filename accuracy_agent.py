import os
import sys
import sqlite3
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report
)

def haversine_distance(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2.0)**2
    c = 2 * np.arcsin(np.sqrt(a))
    r = 6371 # Radius of earth in kilometers
    return c * r

def main():
    print("======================================================================")
    print("                     FRAUD DETECTION MODEL AUDIT                      ")
    print("======================================================================\n")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(base_dir, 'data', 'credit_card_transactions.csv')
    pipeline_path = os.path.join(base_dir, 'backend', 'fraud_model_pipeline.pkl')
    db_path = os.path.join(base_dir, 'transactions.db')

    # -------------------------------------------------------------------------
    # PART A: Ground-truth accuracy on credit_card_transactions.csv
    # -------------------------------------------------------------------------
    print("--- PART A: Ground-Truth Model Accuracy Evaluation ---")
    if not os.path.exists(data_path):
        print(f"ERROR: Dataset not found at {data_path}")
        return
    if not os.path.exists(pipeline_path):
        print(f"ERROR: Pipeline pkl not found at {pipeline_path}")
        return

    print(f"Loading dataset from: {data_path}")
    df = pd.read_csv(data_path)
    
    print("Preprocessing data and engineering features...")
    df = df.drop_duplicates()
    df = df.dropna()
    
    if all(col in df.columns for col in ['lat', 'long', 'merch_lat', 'merch_long']):
        df['distance_from_home'] = haversine_distance(
            df['lat'], df['long'], df['merch_lat'], df['merch_long']
        )
    
    if 'unix_time' in df.columns:
        dt = pd.to_datetime(df['unix_time'], unit='s')
        df['transaction_hour'] = dt.dt.hour
        df['weekend_transaction'] = (dt.dt.dayofweek >= 5).astype(int)
        df['is_night_transaction'] = ((df['transaction_hour'] >= 22) | (df['transaction_hour'] <= 5)).astype(int)

    cols_to_drop = [
        'Unnamed: 0', 'trans_date_trans_time', 'cc_num', 'first', 'last', 
        'dob', 'trans_num', 'unix_time', 'lat', 'long', 'merch_lat', 
        'merch_long', 'street', 'zip', 'job'
    ]
    df = df.drop(columns=[col for col in cols_to_drop if col in df.columns], errors='ignore')

    print("Downsampling data following model/train_model.py logic...")
    fraud_count = df['is_fraud'].sum()
    if fraud_count < 1000:
        df_fraud = df[df['is_fraud'] == 1]
        df_non_fraud = df[df['is_fraud'] == 0].sample(n=min(14000, len(df) - len(df_fraud)), random_state=42)
        df_sample = pd.concat([df_fraud, df_non_fraud]).sample(frac=1, random_state=42)
    else:
        df_sample = df.sample(n=min(20000, len(df)), random_state=42)

    X = df_sample.drop('is_fraud', axis=1)
    y = df_sample['is_fraud']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    print(f"Loading deployed model pipeline from: {pipeline_path}")
    pipeline = joblib.load(pipeline_path)

    print("Running predictions on held-out test split...")
    preds = pipeline.predict(X_test)
    pred_probas = pipeline.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, preds)
    prec = precision_score(y_test, preds, zero_division=0)
    rec = recall_score(y_test, preds)
    f1 = f1_score(y_test, preds)
    roc_auc = roc_auc_score(y_test, pred_probas)
    cm = confusion_matrix(y_test, preds)
    cr = classification_report(y_test, preds)

    print("\nMetrics summary:")
    print(f"Accuracy:  {acc:.4f}")
    print(f"Precision: {prec:.4f}")
    print(f"Recall:    {rec:.4f}")
    print(f"F1 Score:  {f1:.4f}")
    print(f"ROC-AUC:   {roc_auc:.4f}")
    print("\nConfusion Matrix:")
    print(cm)
    print("\nClassification Report:")
    print(cr)
    print("-----------------------------------------------------------------------\n")

    # -------------------------------------------------------------------------
    # PART B: Live agreement rate on transactions.db
    # -------------------------------------------------------------------------
    print("--- PART B: Live Model-vs-Officer Agreement Check ---")
    if not os.path.exists(db_path):
        print(f"INFO: transactions.db not found at {db_path} or no database created yet. Skipping Part B.")
        return

    conn = sqlite3.connect(db_path)
    try:
        # Check if tables exist
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'")
        t_exists = cursor.fetchone()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'")
        r_exists = cursor.fetchone()

        if not t_exists or not r_exists:
            print("INFO: Either 'transactions' or 'reviews' table does not exist yet. Skipping Part B.")
            return

        query = """
            SELECT t.status, t.fraud_probability, r.decision, t.transaction_id
            FROM transactions t
            INNER JOIN reviews r ON t.transaction_id = r.transaction_id
        """
        df_live = pd.read_sql_query(query, conn)
        
        if df_live.empty:
            print("INFO: No reviews recorded in reviews table yet. Skipping Part B.")
            return

        print(f"Total live reviewed transactions found: {len(df_live)}")
        
        # Agreement mapping:
        # APPROVED matches Approved
        # BLOCKED matches Blocked or Flagged
        # VERIFICATION_REQUIRED matches Pending Review or Flagged
        def is_agreement(row):
            model_status = row['status'].lower()
            officer_decision = row['decision'].upper()
            
            if officer_decision == 'APPROVED' and model_status == 'approved':
                return True
            if officer_decision == 'BLOCKED' and model_status in ['blocked', 'flagged']:
                return True
            if officer_decision == 'VERIFICATION_REQUIRED' and model_status in ['pending review', 'flagged']:
                return True
            return False

        df_live['agreed'] = df_live.apply(is_agreement, axis=1)
        agreement_rate = df_live['agreed'].mean() * 100
        
        print("\nBreakdown of Live Joined Records:")
        print(df_live[['status', 'decision']].value_counts())
        
        print(f"\nLive Agreement Rate: {agreement_rate:.2f}%")
        print("\nNOTE: This is an agreement/drift metric between the model's original verdict and")
        print("the bank officer's manual review action. It is not true ground-truth accuracy.")
    except Exception as e:
        print(f"Error checking live database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
