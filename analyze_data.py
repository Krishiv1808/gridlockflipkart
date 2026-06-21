import pandas as pd
import numpy as np
import json
import os

def main():
    print("Starting data ingestion and preprocessing...")
    csv_path = 'round2/jan to may police violation_anonymized791b166.csv'
    
    if not os.path.exists(csv_path):
        print(f"Error: Dataset not found at {csv_path}")
        return
    
    # Load columns of interest to save memory and speed up
    use_cols = ['latitude', 'longitude', 'location', 'vehicle_type', 'violation_type', 'created_datetime', 'police_station']
    print("Reading CSV dataset...")
    df = pd.read_csv(csv_path, usecols=use_cols)
    print(f"Loaded {len(df)} rows.")
    
    # Clean datetime
    print("Processing timestamps...")
    df['created_datetime'] = pd.to_datetime(df['created_datetime'], errors='coerce')
    df = df.dropna(subset=['created_datetime'])
    df['hour'] = df['created_datetime'].dt.hour
    df['day_of_week'] = df['created_datetime'].dt.dayofweek
    df['is_weekend'] = df['day_of_week'].apply(lambda x: 1 if x in [5, 6] else 0)
    df['month'] = df['created_datetime'].dt.month
    
    # Standardize vehicle types and assign congestion weights
    # Congestion Weight: BUS/TRUCK=2.5-3.0, LGV/MAXI-CAB=2.0, CAR=1.5, AUTO=1.2, TWO-WHEELERS=0.5
    print("Mapping vehicle types and congestion weights...")
    vehicle_weights = {
        'SCOOTER': 0.5,
        'MOTOR CYCLE': 0.5,
        'MOPED': 0.5,
        'CAR': 1.5,
        'VAN': 1.5,
        'MAXI-CAB': 2.0,
        'LGV': 2.2,
        'GOODS AUTO': 1.2,
        'PASSENGER AUTO': 1.2,
        'PRIVATE BUS': 3.0,
        'TRUCK': 3.0,
        'TRACTOR': 2.0,
        'TEMPO': 2.0,
        'AUTO RICKSHAW': 1.2,
        'STAGE CARRIAGE': 3.0,
        'AMBULANCE': 1.0,
        'POLICE VEHICLE': 1.0
    }
    
    df['vehicle_type_clean'] = df['vehicle_type'].str.upper().fillna('UNKNOWN')
    # Custom mapping for containing keywords
    def map_weight(v):
        v_upper = str(v).upper()
        for k, w in vehicle_weights.items():
            if k in v_upper:
                return w
        if 'BUS' in v_upper:
            return 3.0
        if 'AUTO' in v_upper:
            return 1.2
        if 'CYCLE' in v_upper or 'BIKE' in v_upper or 'TWO' in v_upper:
            return 0.5
        if 'CAR' in v_upper or 'SUV' in v_upper:
            return 1.5
        if 'TRUCK' in v_upper or 'LORRY' in v_upper:
            return 3.0
        return 1.0

    df['congestion_weight'] = df['vehicle_type_clean'].apply(map_weight)
    
    # 3. Create spatial grid hotspots (round lat/lon to 3 decimal places ~111m)
    print("Clustering violations into spatial hotspots...")
    df['lat_grid'] = df['latitude'].round(3)
    df['lon_grid'] = df['longitude'].round(3)
    
    # Group by lat_grid, lon_grid to find hotspots
    hotspot_groups = df.groupby(['lat_grid', 'lon_grid'])
    
    hotspots_list = []
    
    # We will compute properties for each grid cell
    print("Computing hotspot aggregates...")
    for (lat_g, lon_g), group in hotspot_groups:
        total_violations = len(group)
        if total_violations < 50:  # Filter out low violation areas to keep only hotspots
            continue
            
        # Representative location: most common non-null location
        locs = group['location'].dropna()
        rep_location = locs.value_counts().index[0] if len(locs) > 0 else f"Junction at ({lat_g}, {lon_g})"
        
        # Police station
        stations = group['police_station'].dropna()
        rep_station = stations.value_counts().index[0] if len(stations) > 0 else "Unknown Station"
        
        # Average weight
        avg_weight = group['congestion_weight'].mean()
        
        # Center coordinates
        mean_lat = group['latitude'].mean()
        mean_lon = group['longitude'].mean()
        
        # Vehicle type counts
        v_counts = group['vehicle_type_clean'].value_counts().head(5).to_dict()
        v_counts_json = json.dumps(v_counts)
        
        hotspots_list.append({
            'lat_grid': lat_g,
            'lon_grid': lon_g,
            'latitude': mean_lat,
            'longitude': mean_lon,
            'location': rep_location,
            'police_station': rep_station,
            'total_violations': total_violations,
            'avg_weight': avg_weight,
            'vehicle_distribution': v_counts_json
        })
        
    hotspots_df = pd.DataFrame(hotspots_list)
    # Sort by total violations and select top 150
    hotspots_df = hotspots_df.sort_values(by='total_violations', ascending=False).head(150).reset_index(drop=True)
    hotspots_df['hotspot_id'] = [f"HS_{i:03d}" for i in range(1, len(hotspots_df) + 1)]
    
    # 4. Simulate MapMyIndia traffic speed and compute impact scores
    print("Simulating traffic congestion impact scores...")
    np.random.seed(42)
    # Base speeds and actual speeds simulation
    hotspots_df['free_flow_speed'] = 40.0  # standard speed limit in Bengaluru urban
    # Speed drop is a function of total violation density and average vehicle footprint weight
    # We add some random fluctuation for realism
    speed_drops = (hotspots_df['total_violations'] * 0.015 * hotspots_df['avg_weight']) + np.random.uniform(2.0, 8.0, size=len(hotspots_df))
    # Clip speed drop to max 28 km/h (speeds won't drop below 12 km/h)
    speed_drops = np.clip(speed_drops, 5.0, 28.0)
    
    hotspots_df['actual_speed'] = hotspots_df['free_flow_speed'] - speed_drops
    hotspots_df['speed_reduction'] = (hotspots_df['free_flow_speed'] - hotspots_df['actual_speed']) / hotspots_df['free_flow_speed']
    
    # Calculate Parking Congestion Impact Score (PCIS)
    # PCIS = (Violations * Weight * Speed Reduction * Duration Factor)
    # We assume average parking duration is 25 minutes (simulated baseline)
    avg_duration_mins = 25.0
    # Let's scale active violating vehicles as a fraction of daily violations (say 15% are concurrent during peak hours)
    active_vehicles_factor = 0.15
    
    hotspots_df['congestion_score'] = (
        hotspots_df['total_violations'] * active_vehicles_factor * 
        hotspots_df['avg_weight'] * hotspots_df['speed_reduction'] * 
        (avg_duration_mins / 10.0)
    ).round(1)
    
    # Enforcement priority ranking
    def get_priority(score):
        if score >= 100.0:
            return "CRITICAL"
        elif score >= 40.0:
            return "HIGH"
        else:
            return "NORMAL"
            
    hotspots_df['priority'] = hotspots_df['congestion_score'].apply(get_priority)
    
    print(f"Generated {len(hotspots_df)} hotspots.")
    print("Priority counts:\n", hotspots_df['priority'].value_counts())
    
    # Save hotspots summary
    hotspots_df.to_csv('round2/hotspots_summary.csv', index=False)
    print("Saved hotspots summary to round2/hotspots_summary.csv")
    
    # 5. Generate hourly aggregated dataset for training predictive model
    print("Generating hourly aggregation dataset for training...")
    # Join original data with hotspot IDs
    # Map lat/lon rounded to 3 decimal places to hotspot IDs
    grid_to_hs = hotspots_df.set_index(['lat_grid', 'lon_grid'])['hotspot_id'].to_dict()
    
    # Filter original data to only include records belonging to these top hotspots
    df['hotspot_id'] = df.set_index(['lat_grid', 'lon_grid']).index.map(grid_to_hs)
    df_filtered = df.dropna(subset=['hotspot_id'])
    
    # Group by hotspot_id, hour, day_of_week, month to get historical counts
    hourly_df = df_filtered.groupby(['hotspot_id', 'hour', 'day_of_week', 'month']).size().reset_index(name='violation_count')
    
    # Fill in zeros for missing hour/day combinations to make training set realistic
    all_hotspots = hotspots_df['hotspot_id'].unique()
    all_hours = list(range(24))
    all_days = list(range(7))
    all_months = df['month'].unique()
    
    # Create complete grid
    full_grid = pd.MultiIndex.from_product(
        [all_hotspots, all_hours, all_days, all_months],
        names=['hotspot_id', 'hour', 'day_of_week', 'month']
    ).to_frame().reset_index(drop=True)
    
    # Merge and fill NaN with 0
    training_data = pd.merge(full_grid, hourly_df, on=['hotspot_id', 'hour', 'day_of_week', 'month'], how='left')
    training_data['violation_count'] = training_data['violation_count'].fillna(0).astype(int)
    
    # Let's add some target speed reduction for the hour
    # Speed reduction is higher during peak hours (8-11 AM, 5-8 PM)
    def simulate_hourly_speed_reduction(row):
        h = row['hour']
        base_red = 0.1  # baseline speed reduction
        if 8 <= h <= 11:
            base_red = 0.4
        elif 17 <= h <= 20:
            base_red = 0.5
        elif 12 <= h <= 16:
            base_red = 0.25
        
        # Add violation impact
        violation_impact = min(0.4, row['violation_count'] * 0.05)
        # Random noise
        noise = np.random.normal(0, 0.05)
        return np.clip(base_red + violation_impact + noise, 0.05, 0.8)
        
    training_data['speed_reduction'] = training_data.apply(simulate_hourly_speed_reduction, axis=1)
    
    training_data.to_csv('round2/hourly_violation_counts.csv', index=False)
    print(f"Saved {len(training_data)} rows of training data to round2/hourly_violation_counts.csv")
    print("Preprocessing completed successfully!")

if __name__ == '__main__':
    main()
