# cnn_regression_tf.py

import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Conv1D, Dense, Flatten, InputLayer
import joblib




# Load data
data = pd.read_csv("/home/ayush/aws-proj-flask/data.csv")  
# Columns: cpu, network_in, network_out, ngrok_access, trending_topics, target

features = ['cpu', 'network_in', 'network_out', 'ngrok_access', 'trending_topics']
X = data[features].values
y = data['target'].values.reshape(-1, 1)

# Normalize
scaler_X = MinMaxScaler()
X_scaled = scaler_X.fit_transform(X)

scaler_y = MinMaxScaler()
y_scaled = scaler_y.fit_transform(y)

# Reshape for Conv1D (samples, timesteps, features=1)
X_scaled = X_scaled.reshape((X_scaled.shape[0], X_scaled.shape[1], 1))

# Train/test split
X_train, X_test, y_train, y_test = train_test_split(X_scaled, y_scaled, test_size=0.2, random_state=42)

# Build CNN regression model
model = Sequential([
    InputLayer(input_shape=(X_train.shape[1], 1)),
    Conv1D(filters=16, kernel_size=2, activation='relu'),
    Conv1D(filters=32, kernel_size=2, activation='relu'),
    Flatten(),
    Dense(64, activation='relu'),
    Dense(1)  # Regression output
])

model.compile(optimizer='adam', loss='mse', metrics=['mae'])
model.summary()

# Train model
history = model.fit(
    X_train, y_train,
    validation_data=(X_test, y_test),
    epochs=50,
    batch_size=16
)

# Predictions
preds = model.predict(X_test)
preds_original_scale = scaler_y.inverse_transform(preds)
y_test_original_scale = scaler_y.inverse_transform(y_test)

for i in range(5):
    print(f"Predicted: {preds_original_scale[i][0]:.2f}, Actual: {y_test_original_scale[i][0]:.2f}")

# Export the model
model.save("aws_model.keras")
joblib.dump(scaler_X, "scaler_X.pkl")
joblib.dump(scaler_y, "scaler_y.pkl")
print("Model Saved")
