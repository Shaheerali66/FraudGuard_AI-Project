# FraudGuard – Project Report

## 1. Problem
Credit card fraud costs financial institutions and consumers billions of dollars annually. To combat this, real-time risk assessment at the point of sale (or checkout) is critical. This project addresses the credit card fraud detection problem: taking incoming transaction payload data (e.g. transaction amount, merchant category, time of day, location, and distance from home) and instantly outputting a risk score, classification verdict (Approved, Pending Review, Blocked), and a clear visual explanation of the model's decision.

## 2. Method
- **Dataset**: Built using a sample of `credit_card_transactions.csv` containing over 14,500 downsampled real-world transaction rows.
- **Feature Engineering**: Intermediate features were engineered including calculating the Haversine distance between the customer's coordinates and the merchant's coordinates, identifying night-time transaction windows (10 PM to 5 AM), transaction hour, and flagging weekend transactions.
- **Model Evaluation**: An XGBoost classifier was trained against a Random Forest baseline. Hyperparameter tuning was performed using a randomized search CV to maximize the recall and ROC-AUC of the pipeline, limiting false negatives.
- **Explainability**: SHAP (SHapley Additive exPlanations) values are computed dynamically for every transaction, translating the raw model prediction into positive and negative risk factors which are rendered in the dashboard.
- **Architecture**: Separated into a FastAPI backend service (serving predictions, persisting review decisions to SQLite database using SQLAlchemy) and a Streamlit frontend dashboard (delivering a clean layout with custom CSS themes).

## 3. AI Used
- **Machine Learning**: `xgboost` (classifier), `scikit-learn` (preprocessing pipelines), `joblib` (model serialization), and `shap` (explainability coefficients).
- **Generative AI Assistance**: Claude (Anthropic) used via the Antigravity IDE to assist in development, design, and code optimization.

## 4. Results
The models were evaluated on a held-out test split (20% random stratified split):

| Metric | Random Forest (Baseline) | XGBoost (Production) |
|---|---|---|
| **Accuracy** | 0.9087 | **0.9845** |
| **Precision** | 0.2538 | **0.7615** |
| **Recall** | **0.8235** | 0.8137 |
| **F1-Score** | 0.3880 | **0.7867** |
| **ROC-AUC** | 0.9403 | **0.9872** |

XGBoost was chosen for production deployment due to its superior ROC-AUC (0.9872) and robust F1-score (0.7867) while maintaining high recall (81.37%) on fraud instances.

## 5. Limitations & Future Improvements
1. **Cold Starts**: API endpoints are deployed on free-tier services which may encounter initialization delays; a caching layer or warm ping routine could mitigate this.
2. **Location Accuracy Defaults**: In cases where coordinates are missing, default zip code values are used. Implementing IP-based geolocations would improve accuracy.
3. **Imbalanced Class Weights**: Although downsampling was applied during training, further testing with advanced sampling techniques (such as SMOTE) could improve precision.
