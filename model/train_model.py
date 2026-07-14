import os
import sys
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split, RandomizedSearchCV, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
import shap
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
    """Calculate the great circle distance between two points on the earth."""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2.0)**2
    c = 2 * np.arcsin(np.sqrt(a))
    r = 6371 # Radius of earth in kilometers
    return c * r

def load_data(file_path):
    if not os.path.exists(file_path):
        print(f"ERROR: Dataset not found at {file_path}")
        sys.exit(1)
    print(f"Loading dataset from {file_path}...")
    df = pd.read_csv(file_path)
    return df

def preprocess_and_engineer_features(df):
    print("Cleaning data and engineering features...")
    df = df.drop_duplicates()
    df = df.dropna()
    
    if all(col in df.columns for col in ['lat', 'long', 'merch_lat', 'merch_long']):
        df['distance_from_home'] = haversine_distance(
            df['lat'], df['long'], df['merch_lat'], df['merch_long']
        )
    
    if 'unix_time' in df.columns:
        dt = pd.to_datetime(df['unix_time'], unit='s')
        df['transaction_hour'] = dt.dt.hour
        df['weekend_transaction'] = dt.dt.dayofweek >= 5
        df['is_night_transaction'] = ((df['transaction_hour'] >= 22) | (df['transaction_hour'] <= 5)).astype(int)
        df['weekend_transaction'] = df['weekend_transaction'].astype(int)

    cols_to_drop = [
        'Unnamed: 0', 'trans_date_trans_time', 'cc_num', 'first', 'last', 
        'dob', 'trans_num', 'unix_time', 'lat', 'long', 'merch_lat', 
        'merch_long', 'street', 'zip', 'job'
    ]
    df = df.drop(columns=[col for col in cols_to_drop if col in df.columns], errors='ignore')
    
    return df

def get_preprocessor(X):
    categorical_cols = X.select_dtypes(include=['object', 'category']).columns.tolist()
    numerical_cols = X.select_dtypes(exclude=['object', 'category']).columns.tolist()
    
    numeric_transformer = StandardScaler()
    categorical_transformer = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numerical_cols),
            ('cat', categorical_transformer, categorical_cols)
        ]
    )
    return preprocessor

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(base_dir, 'data', 'credit_card_transactions.csv')
    
    df = load_data(data_path)
    df = preprocess_and_engineer_features(df)
    
    # Stratified downsample to 15,000 rows to ensure fast tuning & SHAP fitting under constraint
    print("Downsampling data for faster model selection and SHAP fitting...")
    df_sample = df.groupby('is_fraud', group_keys=False).apply(lambda x: x.sample(min(len(x), 10000), random_state=42))
    # If the fraud records are sparse, let's keep all fraud records and sample non-fraud
    fraud_count = df['is_fraud'].sum()
    if fraud_count < 1000:
        # keep all fraud, sample 14,000 non-fraud
        df_fraud = df[df['is_fraud'] == 1]
        df_non_fraud = df[df['is_fraud'] == 0].sample(n=min(14000, len(df) - len(df_fraud)), random_state=42)
        df_sample = pd.concat([df_fraud, df_non_fraud]).sample(frac=1, random_state=42)
    else:
        df_sample = df.sample(n=min(20000, len(df)), random_state=42)
        
    print(f"Sampled shape: {df_sample.shape} | Fraud count: {df_sample['is_fraud'].sum()}")

    if 'is_fraud' not in df_sample.columns:
        print("ERROR: Target column 'is_fraud' not found in dataset.")
        sys.exit(1)
        
    X = df_sample.drop('is_fraud', axis=1)
    y = df_sample['is_fraud']
    
    print("Splitting dataset into training and testing sets...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    preprocessor = get_preprocessor(X_train)
    X_train_trans = preprocessor.fit_transform(X_train)
    X_test_trans = preprocessor.transform(X_test)
    
    # Get feature names out
    feature_names = preprocessor.get_feature_names_out().tolist()
    # Clean up feature names to be more human readable
    readable_feature_names = []
    for name in feature_names:
        name = name.replace("num__", "").replace("cat__", "")
        # replace category prefix with a space or colon
        name = name.replace("gender_", "Gender: ").replace("merchant_category_", "Merchant Category: ").replace("city_", "City: ").replace("state_", "State: ").replace("merchant_", "Merchant: ")
        readable_feature_names.append(name)
        
    # Class imbalance weight for XGBoost
    neg_count = (y_train == 0).sum()
    pos_count = (y_train == 1).sum()
    scale_weight = neg_count / pos_count if pos_count > 0 else 1.0
    
    print(f"Negative samples: {neg_count}, Positive samples: {pos_count}, Scale weight: {scale_weight:.4f}")
    
    cv_split = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    
    # ── Candidate A: Random Forest ───────────────────────────────────────────
    print("Tuning RandomForestClassifier...")
    rf_param_grid = {
        'n_estimators': [50, 100, 150],
        'max_depth': [5, 10, 15, None],
        'min_samples_split': [2, 5, 10],
        'min_samples_leaf': [1, 2, 4],
        'class_weight': ['balanced', 'balanced_subsample', None]
    }
    rf_search = RandomizedSearchCV(
        RandomForestClassifier(random_state=42, n_jobs=-1),
        param_distributions=rf_param_grid,
        n_iter=1,
        scoring='roc_auc',
        cv=cv_split,
        random_state=42,
        n_jobs=-1
    )
    rf_search.fit(X_train_trans, y_train)
    best_rf = rf_search.best_estimator_
    
    # ── Candidate B: XGBoost ─────────────────────────────────────────────────
    print("Tuning XGBClassifier...")
    xgb_param_grid = {
        'n_estimators': [50, 100, 150],
        'max_depth': [3, 5, 7, 10],
        'learning_rate': [0.01, 0.05, 0.1, 0.2],
        'subsample': [0.6, 0.8, 1.0]
    }
    xgb_search = RandomizedSearchCV(
        XGBClassifier(random_state=42, scale_pos_weight=scale_weight, n_jobs=-1, eval_metric='logloss'),
        param_distributions=xgb_param_grid,
        n_iter=1,
        scoring='roc_auc',
        cv=cv_split,
        random_state=42,
        n_jobs=-1
    )
    xgb_search.fit(X_train_trans, y_train)
    best_xgb = xgb_search.best_estimator_
    
    # ── Evaluate Candidates on Test Set ──────────────────────────────────────
    print("Evaluating models on test set...")
    rf_pred = best_rf.predict(X_test_trans)
    rf_pred_proba = best_rf.predict_proba(X_test_trans)[:, 1]
    
    xgb_pred = best_xgb.predict(X_test_trans)
    xgb_pred_proba = best_xgb.predict_proba(X_test_trans)[:, 1]
    
    rf_metrics = {
        'name': 'Random Forest',
        'accuracy': accuracy_score(y_test, rf_pred),
        'precision': precision_score(y_test, rf_pred, zero_division=0),
        'recall': recall_score(y_test, rf_pred),
        'f1': f1_score(y_test, rf_pred),
        'roc_auc': roc_auc_score(y_test, rf_pred_proba),
        'cm': confusion_matrix(y_test, rf_pred),
        'cr': classification_report(y_test, rf_pred),
        'model': best_rf
    }
    
    xgb_metrics = {
        'name': 'XGBoost',
        'accuracy': accuracy_score(y_test, xgb_pred),
        'precision': precision_score(y_test, xgb_pred, zero_division=0),
        'recall': recall_score(y_test, xgb_pred),
        'f1': f1_score(y_test, xgb_pred),
        'roc_auc': roc_auc_score(y_test, xgb_pred_proba),
        'cm': confusion_matrix(y_test, xgb_pred),
        'cr': classification_report(y_test, xgb_pred),
        'model': best_xgb
    }
    
    print("\n--- Model Comparison ---")
    print(f"{'Metric':<12} | {'Random Forest':<15} | {'XGBoost':<15}")
    print("-" * 50)
    for m in ['accuracy', 'precision', 'recall', 'f1', 'roc_auc']:
        print(f"{m.capitalize():<12} | {rf_metrics[m]:.4f}{'':<11} | {xgb_metrics[m]:.4f}")
    
    # Select best model by ROC-AUC
    best = xgb_metrics if xgb_metrics['roc_auc'] >= rf_metrics['roc_auc'] else rf_metrics
    print(f"\nBest Model Selected: {best['name']} (ROC-AUC: {best['roc_auc']:.4f})")
    
    # Save training report
    report_path = os.path.join(base_dir, 'model', 'training_report.txt')
    with open(report_path, 'w') as f:
        f.write("=== FRAUD DETECTION MODEL TRAINING REPORT ===\n\n")
        f.write(f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Training dataset: {data_path} (Downsampled to {len(df_sample)} rows)\n\n")
        f.write("Candidate Comparison Table:\n")
        f.write(f"{'Metric':<12} | {'Random Forest':<15} | {'XGBoost':<15}\n")
        f.write("-" * 50 + "\n")
        for m in ['accuracy', 'precision', 'recall', 'f1', 'roc_auc']:
            f.write(f"{m.capitalize():<12} | {rf_metrics[m]:.4f}{'':<11} | {xgb_metrics[m]:.4f}\n")
        f.write("\n" + "=" * 50 + "\n")
        f.write(f"Chosen Model: {best['name']}\n")
        f.write("=" * 50 + "\n\n")
        f.write("Confusion Matrix:\n")
        f.write(str(best['cm']) + "\n\n")
        f.write("Classification Report:\n")
        f.write(best['cr'] + "\n")
        
    print(f"Saved training report to {report_path}")
    
    # Build best pipeline
    final_pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('classifier', best['model'])
    ])
    
    # Save the pipeline
    model_output_path = os.path.join(base_dir, 'backend', 'fraud_model_pipeline.pkl')
    os.makedirs(os.path.dirname(model_output_path), exist_ok=True)
    joblib.dump(final_pipeline, model_output_path)
    print(f"Saved best pipeline to {model_output_path}")
    
    # Save readable feature names
    feature_names_path = os.path.join(base_dir, 'backend', 'feature_names.pkl')
    joblib.dump(readable_feature_names, feature_names_path)
    print(f"Saved readable feature names to {feature_names_path}")
    
    # Fit SHAP explainer on classifier using backgrounds
    print("Fitting SHAP TreeExplainer...")
    explainer = shap.TreeExplainer(best['model'])
    
    explainer_path = os.path.join(base_dir, 'backend', 'shap_explainer.pkl')
    joblib.dump(explainer, explainer_path)
    print(f"Saved SHAP TreeExplainer to {explainer_path}")
    print("Training script completed successfully.")

if __name__ == "__main__":
    main()
