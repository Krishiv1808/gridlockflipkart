import pandas as pd
import numpy as np
import pickle
import os
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score
from sklearn.preprocessing import LabelEncoder

def main():
    print("Starting Predictive AI model training...")
    data_path = 'round2/hourly_violation_counts.csv'
    
    if not os.path.exists(data_path):
        print(f"Error: Training data not found at {data_path}")
        return
        
    df = pd.read_csv(data_path)
    print(f"Loaded {len(df)} rows of training data.")
    
    # 1. Feature Engineering
    # Extract hotspot numeric ID from hotspot_id (e.g. HS_001 -> 1)
    df['hotspot_num'] = df['hotspot_id'].apply(lambda x: int(x.split('_')[1]))
    
    # Cyclical hour features
    df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24.0)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24.0)
    
    # Cyclical day of week features
    df['day_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7.0)
    df['day_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7.0)
    
    # Features & Targets
    features = ['hotspot_num', 'hour', 'day_of_week', 'month', 'hour_sin', 'hour_cos', 'day_sin', 'day_cos']
    target_violations = 'violation_count'
    target_speed = 'speed_reduction'
    
    X = df[features]
    y_violations = df[target_violations]
    y_speed = df[target_speed]
    
    # Split train/test
    X_train, X_test, y_train_v, y_test_v, y_train_s, y_test_s = train_test_split(
        X, y_violations, y_speed, test_size=0.2, random_state=42
    )
    
    print(f"Train size: {X_train.shape[0]}, Test size: {X_test.shape[0]}")
    
    # Try importing LightGBM; if not available, fallback to Random Forest
    try:
        import lightgbm as lgb
        print("Using LightGBM Regressor for training...")
        
        # Model for violations
        model_v = lgb.LGBMRegressor(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=31,
            random_state=42,
            verbose=-1
        )
        model_v.fit(X_train, y_train_v)
        preds_v = model_v.predict(X_test)
        r2_v = r2_score(y_test_v, preds_v)
        print(f"Violations Prediction Model - Test R2 Score: {r2_v:.4f}")
        
        # Model for speed reduction
        model_s = lgb.LGBMRegressor(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=31,
            random_state=42,
            verbose=-1
        )
        model_s.fit(X_train, y_train_s)
        preds_s = model_s.predict(X_test)
        r2_s = r2_score(y_test_s, preds_s)
        print(f"Speed Reduction Model - Test R2 Score: {r2_s:.4f}")
        
    except ImportError:
        print("LightGBM not available. Falling back to Scikit-Learn Gradient Boosting...")
        from sklearn.ensemble import GradientBoostingRegressor
        
        model_v = GradientBoostingRegressor(n_estimators=100, max_depth=5, random_state=42)
        model_v.fit(X_train, y_train_v)
        preds_v = model_v.predict(X_test)
        r2_v = r2_score(y_test_v, preds_v)
        print(f"Violations Model - Test R2 Score: {r2_v:.4f}")
        
        model_s = GradientBoostingRegressor(n_estimators=100, max_depth=5, random_state=42)
        model_s.fit(X_train, y_train_s)
        preds_s = model_s.predict(X_test)
        r2_s = r2_score(y_test_s, preds_s)
        print(f"Speed Reduction Model - Test R2 Score: {r2_s:.4f}")
        
    # Save both models and the list of features in a dict
    model_package = {
        'model_violations': model_v,
        'model_speed': model_s,
        'features': features
    }
    
    model_path = 'round2/predictor_model.pkl'
    with open(model_path, 'wb') as f:
        pickle.dump(model_package, f)
    print(f"Saved trained model packages to {model_path}")
    print("Training process completed successfully!")

if __name__ == '__main__':
    main()
