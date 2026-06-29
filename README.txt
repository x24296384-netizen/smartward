SmartWard — IoT Patient Monitoring System
NCI MSc Cloud Computing 2026 | Fog and Edge Computing (H9FECC)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SmartWard simulates a hospital ward IoT monitoring system using a
three-layer fog/edge computing architecture:

  Sensor Layer  → three mock sensors (heart rate, SpO2, environment)
  Fog Layer     → virtual fog node (Python HTTP server + SQS dispatcher)
  Cloud Layer   → AWS SQS + Lambda + DynamoDB + API Gateway + dashboard

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROJECT STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

smartward/
├── sensors/
│   ├── heart_rate_sensor.py      Mock heart rate sensor (bpm)
│   ├── spo2_sensor.py            Mock blood oxygen sensor (%)
│   └── environment_sensor.py     Mock temp + humidity sensor
├── fog_node/
│   └── fog_node.py               Virtual fog node (HTTP + SQS dispatch)
├── backend/
│   └── lambda_functions/
│       ├── sqs_processor.py      Lambda: SQS → DynamoDB + SNS alerts
│       └── dashboard_api.py      Lambda: API Gateway → DynamoDB query
├── dashboard/
│   └── index.html                Single-page live monitoring dashboard
├── infrastructure/
│   └── setup_infrastructure.py   Creates AWS resources (run once)
├── .github/workflows/
│   └── ci-cd.yml                 GitHub Actions pipeline
└── README.txt                    This file

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PREREQUISITES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Python 3.10+
- AWS CLI configured (AWS Academy credentials)
- boto3: pip install boto3

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1 — AWS SETUP (run once)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Set your AWS Academy credentials in ~/.aws/credentials or via:
     export AWS_ACCESS_KEY_ID=...
     export AWS_SECRET_ACCESS_KEY=...
     export AWS_SESSION_TOKEN=...

2. Run the infrastructure setup script:
     python infrastructure/setup_infrastructure.py

   This creates:
     - DynamoDB table: smartward-readings (PAY_PER_REQUEST, TTL enabled)
     - SQS queue: smartward-sensor-queue
     - SNS topic: smartward-alerts

3. Copy the exported environment variables it prints.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2 — DEPLOY LAMBDA FUNCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Create two Lambda functions in the AWS Console (Python 3.12 runtime):

  Function 1: smartward-sqs-processor
    - Source: backend/lambda_functions/sqs_processor.py
    - Trigger: SQS queue (smartward-sensor-queue), batch size 5
    - Env vars: DYNAMODB_TABLE=smartward-readings
                SNS_TOPIC_ARN=<your-topic-arn>
    - Timeout: 30s | Memory: 256MB

  Function 2: smartward-dashboard-api
    - Source: backend/lambda_functions/dashboard_api.py
    - Trigger: API Gateway (HTTP API)
    - Env vars: DYNAMODB_TABLE=smartward-readings
    - Timeout: 10s | Memory: 128MB
    - Routes: GET /readings, GET /alerts

Note: Uploading via GitHub Actions (push to main) also deploys automatically.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3 — RUN THE FOG NODE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Set environment variables (from Step 1 output), then:

  export SQS_QUEUE_URL='https://sqs.us-east-1.amazonaws.com/...'
  export DYNAMODB_TABLE='smartward-readings'
  export AWS_REGION='us-east-1'
  export BATCH_INTERVAL=10       # seconds between SQS dispatches
  export FOG_PORT=5000

  python fog_node/fog_node.py

The fog node listens on http://localhost:5000/ingest
Health check: http://localhost:5000/health

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4 — RUN THE SENSORS (separate terminals)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Terminal 1:
  PATIENT_ID=P001 SENSOR_ID=HR-01 HEART_RATE_INTERVAL=2 \
    python sensors/heart_rate_sensor.py

Terminal 2:
  PATIENT_ID=P001 SENSOR_ID=SPO2-01 SPO2_INTERVAL=3 \
    python sensors/spo2_sensor.py

Terminal 3:
  WARD_ID=WARD-A SENSOR_ID=ENV-01 ENV_INTERVAL=10 \
    python sensors/environment_sensor.py

To simulate an alert: set SPO2_INTERVAL to 1 — the 4% anomaly rate
will trigger a critical reading within ~25 seconds.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5 — VIEW THE DASHBOARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Option A — Local (no S3): Open dashboard/index.html in a browser.
  Edit the API_BASE variable at the top of the script section to your
  API Gateway URL, or use a local proxy if running dashboard_api locally.

Option B — S3 static hosting:
  aws s3 sync dashboard/ s3://YOUR-BUCKET-NAME/ --delete
  Enable static website hosting on the bucket.
  Access at: http://YOUR-BUCKET-NAME.s3-website-us-east-1.amazonaws.com

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIGURABLE PARAMETERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

All configurable via environment variables:

  FOG_HOST              Fog node bind address (default: 0.0.0.0)
  FOG_PORT              Fog node port (default: 5000)
  SQS_QUEUE_URL         SQS queue URL (required)
  AWS_REGION            AWS region (default: us-east-1)
  BATCH_INTERVAL        Seconds between SQS dispatches (default: 10)
  MAX_BATCH_SIZE        Max readings per SQS message (default: 20)
  HEART_RATE_INTERVAL   Heart rate sensor send rate seconds (default: 2)
  SPO2_INTERVAL         SpO2 sensor send rate seconds (default: 3)
  ENV_INTERVAL          Environment sensor send rate seconds (default: 10)
  PATIENT_ID            Patient ID for HR/SpO2 sensors (default: P001)
  WARD_ID               Ward ID for environment sensor (default: WARD-A)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REUSE FROM PRIOR WORK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The following components are adapted from the ToolLend project
(NCI Cloud Platform Programming CA, April 2026):

  - SQS message dispatch pattern (fog_node.py → sqs_processor.py)
  - SNS alert publishing (sqs_processor.py)
  - DynamoDB write pattern (sqs_processor.py)
  - GitHub Actions CI/CD pipeline structure (ci-cd.yml)
  - CloudWatch logging configuration

All reuse is cited in the project report (Section IV, Implementation).
