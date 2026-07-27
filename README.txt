SmartWard - Installation Instructions
=======================================

PREREQUISITES
--------------
- Python 3.12+ installed
- An AWS account (AWS Academy Learner Lab or equivalent) with access to:
  SQS, Lambda, DynamoDB, SNS, API Gateway, S3
- AWS CLI configured with valid credentials
- Git

REPOSITORY STRUCTURE
---------------------
sensors/              - Five Python sensor scripts (heart_rate, spo2,
                         blood_pressure, respiratory_rate, environment)
fog_node/              - Fog node HTTP server (fog_node.py)
backend/lambda_functions/
                       - sqs_processor.py (SQS -> DynamoDB + SNS)
                       - dashboard_api.py (API Gateway -> DynamoDB reads)
dashboard/             - index.html (live monitoring dashboard, deployed to S3)
.github/workflows/     - CI/CD pipeline (ci-cd.yml)
tests/                 - pytest unit tests

AWS SETUP (one-time, manual via AWS Console)
----------------------------------------------
1. Create an SQS standard queue named "smartward-sensor-queue".
2. Create a DynamoDB table named "smartward-readings":
   - Partition key: pk (String)
   - Sort key: sk (String)
   - Capacity mode: On-demand
   - Enable Time to Live (TTL) on attribute "ttl"
3. Create an SNS topic named "smartward-alerts". Subscribe an email
   address to receive alert notifications (confirm the subscription
   via the email AWS sends).
4. Create two Lambda functions (Python 3.12 runtime):
   - smartward-sqs-processor
     Handler: sqs_processor.lambda_handler
     Trigger: SQS (smartward-sensor-queue)
     Environment variables:
       DYNAMODB_TABLE = smartward-readings
       SNS_TOPIC_ARN  = <ARN of smartward-alerts topic>
   - smartward-dashboard-api
     Handler: dashboard_api.lambda_handler
     Trigger: API Gateway
     Environment variables:
       DYNAMODB_TABLE = smartward-readings
5. Create an API Gateway (HTTP API) named "smartward-api" with two
   routes: GET /readings and GET /alerts, both pointing to
   smartward-dashboard-api. Deploy a stage (e.g. "prod").
6. Create an S3 bucket (e.g. "smartward-dashboard-2026") with static
   website hosting enabled. Upload dashboard/index.html as "index.html".
7. In dashboard/index.html, set the API_BASE constant to your API
   Gateway's invoke URL.

RUNNING LOCALLY
----------------
1. Clone the repository:
     git clone https://github.com/x24296384-netizen/smartward.git
     cd smartward

2. Install dependencies:
     pip install -r requirements.txt --break-system-packages

3. Configure AWS credentials (one-time per session):
     aws configure set aws_access_key_id YOUR_KEY
     aws configure set aws_secret_access_key YOUR_SECRET
     aws configure set aws_session_token YOUR_TOKEN   (if using
       temporary credentials, e.g. AWS Academy)

4. Set environment variables and start the fog node:
     $env:SQS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/<account-id>/smartward-sensor-queue"
     $env:AWS_DEFAULT_REGION="us-east-1"
     python fog_node/fog_node.py

5. In separate terminal windows, start each sensor:
     python sensors/heart_rate_sensor.py
     python sensors/spo2_sensor.py
     python sensors/blood_pressure_sensor.py
     python sensors/respiratory_rate_sensor.py
     python sensors/environment_sensor.py

6. Open the dashboard in a browser at your S3 static website URL to
   view live readings and alerts.

RUNNING TESTS
--------------
     pytest tests/

CI/CD
-----
Pushing to the "main" branch automatically triggers GitHub Actions,
which lints the code (flake8), runs the pytest suite, and deploys the
updated Lambda functions to AWS. See .github/workflows/ci-cd.yml.

NOTES
-----
- Sensor read/dispatch intervals and anomaly rates can be adjusted via
  environment variables in each sensor script.
- AWS Academy temporary credentials expire periodically; if you see
  authentication errors, refresh your credentials and restart the fog
  node in a fresh terminal session (old credentials cached as
  environment variables in an existing terminal can override the
  refreshed credentials file).
