import time
import boto3
import requests
import random
from textblob import TextBlob
from datetime import datetime, timedelta
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import load_model
import joblib
import json

lambda_client = boto3.client('lambda', region_name='ap-south-1') 

LAMBDA_FUNCTION_NAME = 'sportechscale'

scaler_X = joblib.load("/home/ayush/aws-proj-flask/scaler_X.pkl")
scaler_y = joblib.load("/home/ayush/aws-proj-flask/scaler_y.pkl")

# AWS CloudWatch Settings
INSTANCE_ID = 'i-0e654bd116fca55be'
REGION = 'ap-south-1'
EC2_METRICS = ['CPUUtilization', 'NetworkIn', 'NetworkOut']

# Gnews API
API_KEY = "74301bbff9419d78c66b32a60f4679bb"
SPORTS_CATEGORIES = {
    "football": '"Football" OR "Soccer" OR "Premier League"',
    "cricket": '"Cricket" OR "IPL" OR "T20 World Cup"',
    "basketball": '"Basketball" OR "NBA"',
}

NGROK_MIN_HITS = 0
NGROK_MAX_HITS = 15
UPDATE_INTERVAL = 60  

# Load model and scalers
MODEL_PATH = "/home/ayush/aws-proj-flask/aws_model.keras"
model = load_model(MODEL_PATH)

 

cloudwatch = boto3.client('cloudwatch', region_name=REGION)

def fetch_ec2_metrics():
    data_points = {}
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(seconds=UPDATE_INTERVAL)

    for metric_name in EC2_METRICS:
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/EC2', MetricName=metric_name,
            Dimensions=[{'Name': 'InstanceId', 'Value': INSTANCE_ID}],
            StartTime=start_time, EndTime=end_time,
            Period=UPDATE_INTERVAL, Statistics=['Average']
        )

        key_name = metric_name.replace("CPUUtilization", "cpu").replace("Network", "network_").lower()

        if response['Datapoints']:
            latest_point = max(response['Datapoints'], key=lambda x: x['Timestamp'])
            data_points[key_name] = latest_point['Average']
        else:
            data_points[key_name] = 0.0
    return data_points

def get_hype_score(query):
    url = f"https://gnews.io/api/v4/search?q={query}&lang=en&period=1d&apikey={API_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        articles = response.json().get('articles', [])
    except requests.exceptions.RequestException:
        return 0.0

    if not articles:
        return 0.0

    count = len(articles)
    sentiment = sum(TextBlob(a.get('title', '')).sentiment.polarity for a in articles)
    avg_sentiment = sentiment / count if count > 0 else 0.0
    
    return count * (1 + abs(avg_sentiment))

try:
    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{timestamp}] Fetching new metrics...")

        # 1. EC2 metrics
        metrics = fetch_ec2_metrics()

        # 2. Trending topics
        total_hype_score = 0
        for sport, query in SPORTS_CATEGORIES.items():
            total_hype_score += get_hype_score(query)
        metrics['trending_topics'] = round(total_hype_score, 2)

        # 3. Ngrok hits
        metrics['ngrok_access'] = random.randint(NGROK_MIN_HITS, NGROK_MAX_HITS)

        # Prepare model input
        feature_order = ['cpu', 'network_in', 'network_out', 'ngrok_access', 'trending_topics']
        X = np.array([metrics[f] for f in feature_order]).reshape(1, -1)
        X_scaled = scaler_X.transform(X)
        X_scaled = X_scaled.reshape((X_scaled.shape[0], X_scaled.shape[1], 1))

        # Predict EC2 instances
        pred_scaled = model.predict(X_scaled)
        pred = scaler_y.inverse_transform(pred_scaled)[0][0]
        predicted_instances = int(pred)
        payload = {
            "required_instances": predicted_instances
        }

        response = lambda_client.invoke(
            FunctionName=LAMBDA_FUNCTION_NAME,
            InvocationType='Event',  # 'Event' = async, 'RequestResponse' = wait for response
            Payload=json.dumps(payload)
        )


        print(f"Predicted EC2 instances: {pred:.2f}")
        time.sleep(UPDATE_INTERVAL)

except KeyboardInterrupt:
    print("Stopped by user.")
