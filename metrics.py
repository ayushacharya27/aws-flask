import boto3
from datetime import datetime, timedelta

# Create CloudWatch client
cloudwatch = boto3.client('cloudwatch', region_name='YOUR_REGION')

# Replace with your EC2 instance ID
INSTANCE_ID = 'i-0abcd1234efgh5678'

# Metrics to fetch
metrics = {
    'CPU': 'cpu_usage_idle',
    'Memory': 'mem_used_percent',
    'Swap': 'swap_used_percent',
    'DiskUsed': 'disk_used_percent',
    'DiskInodesFree': 'inodes_free',
    'DiskIO': 'io_time'
}

# Time range
start_time = datetime.utcnow() - timedelta(hours=1)
end_time = datetime.utcnow()
period = 60  # seconds

# Fetch metrics
for name, metric_name in metrics.items():
    response = cloudwatch.get_metric_statistics(
        Namespace='CWAgent',
        MetricName=metric_name,
        Dimensions=[
            {'Name': 'InstanceId', 'Value': INSTANCE_ID}
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=period,
        Statistics=['Average']
    )
    
    print(f"\n{name} Metrics:")
    for point in sorted(response['Datapoints'], key=lambda x: x['Timestamp']):
        print(point['Timestamp'], point['Average'])
