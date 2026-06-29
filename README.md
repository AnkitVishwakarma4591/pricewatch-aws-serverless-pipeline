# PriceWatch — Serverless Crypto Price Monitoring Pipeline

PriceWatch is a fully automated, serverless data pipeline that fetches live cryptocurrency prices every 15 minutes, validates the data, stores it in a database, and sends an email alert if a price crosses a defined threshold — all without a single server to manage, and without any manual intervention after deployment.

It was built as a hands-on project to apply real-world data engineering and DevOps concepts: event-driven architecture, data validation, serverless compute, and a versioned, zero-downtime CI/CD deployment pattern.

---

## 1. What problem does this solve?

Manually checking crypto prices, or running a script on your own laptop to "watch" them, doesn't scale — your laptop has to stay on, and there's no record of price history. PriceWatch solves this by running entirely on AWS infrastructure that is:

- **Always on** — runs on a schedule in the cloud, independent of any personal machine
- **Self-healing on bad data** — if the price API returns something unexpected, the pipeline skips that one record instead of crashing entirely
- **Auditable** — every price fetch is stored with a timestamp, building a historical record over time
- **Safely upgradable** — new code can be deployed without any downtime or risk to the live, running version

---

## 2. Architecture

```
 ┌──────────────────┐
 │   EventBridge     │   Cron-like rule: fires every 15 minutes
 │  (scheduler)      │
 └─────────┬─────────┘
           │ triggers
           ▼
 ┌──────────────────────────────┐        ┌──────────────────────┐
 │   AWS Lambda                  │──────▶ │   CoinGecko API       │
 │   (pricewatch-fetcher:prod)   │ fetch  │   (public, free)      │
 │                                │◀────── │   live USD prices     │
 │   1. Calls CoinGecko API      │
 │   2. Validates each price     │
 │   3. Writes valid rows        │───────▶ ┌──────────────────────┐
 │   4. Publishes alert if       │         │   Amazon DynamoDB     │
 │      threshold crossed or     │         │   (crypto-prices)     │
 │      validation fails         │         └──────────────────────┘
 └───────────────┬────────────────┘
                 │ publish (on alert / on error)
                 ▼
 ┌──────────────────────┐
 │   Amazon SNS           │──────▶  Email to subscriber
 │   (pricewatch-alerts)  │
 └──────────────────────┘
```

**Flow in one sentence:** EventBridge wakes Lambda up on a timer → Lambda asks CoinGecko for prices → checks the data is sane → saves it to DynamoDB → emails an alert through SNS only when something noteworthy (a price threshold, or a validation failure) happens.

---

## 3. Tech stack

| Layer | Technology | Why |
|---|---|---|
| Compute | AWS Lambda (Python 3.12) | Serverless — no servers to patch or pay for when idle |
| Scheduler | Amazon EventBridge | Cron-like trigger, fully managed |
| Database | Amazon DynamoDB | Serverless NoSQL, pay-per-request billing, scales automatically |
| Notifications | Amazon SNS | Pub/sub messaging — one topic, one email subscriber today, can fan out to more channels later |
| Permissions | AWS IAM | Least-privilege role — Lambda can only touch the exact table, topic, and logs it needs |
| Data source | CoinGecko public API | Free, no API key required, real live data |
| Deployment | AWS CLI + Windows Batch script | Reproducible, scriptable deploys from the command line |
| Language libraries | `boto3` (AWS SDK), `urllib` (HTTP calls), `decimal` (precise price math) | Standard, no extra dependencies to package |

---

## 4. Core concepts explained simply

If you're new to AWS, here's what each piece actually does — explained without jargon.

### AWS Lambda
Think of Lambda as a function that lives in the cloud and only "wakes up" when something calls it. You don't rent a server 24/7 — you just write a function, and AWS runs it on demand. You pay only for the few seconds it actually executes.

### Amazon EventBridge
This is essentially a cloud alarm clock. You tell it "ring every 15 minutes," and it calls your Lambda function automatically — no human, no cron job on a personal machine, no laptop that needs to stay switched on.

### Amazon DynamoDB
A simple, fast, key-based database. Here, every price is saved with two keys: `coin_id` (e.g. "bitcoin") and `timestamp` (when it was fetched). Together they make each row unique, so the table naturally builds a price history over time.

### Amazon SNS (Simple Notification Service)
Imagine a broadcast list: you publish one message to a "topic," and everyone subscribed to that topic gets a copy — by email, SMS, or another service. Here, one topic (`pricewatch-alerts`) has one email subscriber, but it could be extended to notify a whole team without changing any code.

### IAM Role
A role is a strict permission slip. The Lambda function here can only: write to the one specific DynamoDB table, publish to the one specific SNS topic, and write its own logs. It cannot touch any other AWS resource in the account — this is the principle of least privilege.

### Data validation layer
Before any price is saved, it's checked: does the API response actually contain this coin? Does it have a USD price? Is that price a sane positive number? If not, that one coin is skipped and logged as an error — the rest of the pipeline keeps running. This pattern exists because real-world data is never 100% reliable, and a pipeline should never crash entirely over one bad record.

### Lambda versions & aliases (the deployment safety net)
Every time new code is deployed, it first lands in a draft slot called `$LATEST`. A **version** is a permanent, numbered snapshot of `$LATEST` at a point in time — it never changes once created. An **alias** (here, `prod`) is a movable label that always points to one specific version. EventBridge and all live traffic call the function through the `prod` alias, never `$LATEST` directly. This means deploying new code never risks live traffic — the alias only moves to the new version after it's confirmed published, and if something goes wrong, the alias can be pointed straight back to the previous version.

---

## 5. Project structure

```
PriceWatch/
├── lambda/
│   └── pricewatch/
│       ├── lambda_function.py   # Orchestration: fetch API → validate → save → alert
│       └── transform.py         # Pure validation/business logic, unit-testable
├── trust-policy.json             # IAM trust policy (lets Lambda assume the role)
├── permissions-policy.json       # IAM permissions (DynamoDB, SNS, Logs access)
├── environment.json              # Lambda environment variables
├── targets.json                  # EventBridge → Lambda target mapping
├── deploy.bat                    # One-command CI/CD: zip → deploy → version → alias
└── README.md
```

---

## 6. How the pipeline runs, step by step

1. **EventBridge rule** `pricewatch-schedule` fires every 15 minutes (`rate(15 minutes)`).
2. It invokes the Lambda function through its `prod` alias (not `$LATEST` — see versioning above).
3. Inside the function:
   - `urllib.request` calls the CoinGecko API for the coins listed in the `COINS` environment variable (currently `bitcoin,ethereum`).
   - For each coin, `transform.validate_price()` checks the response is well-formed before anything is saved.
   - Valid prices are written to DynamoDB via `boto3`, using `Decimal` (DynamoDB doesn't support native floats).
   - `transform.crossed_threshold()` checks if the price has crossed `PRICE_THRESHOLD_USD`. If so, an alert is published to SNS.
   - If any coin fails validation, a separate error alert is published, listing exactly what failed.
4. SNS delivers any published message to the subscribed email instantly.

---

## 7. Deployment / CI-CD (`deploy.bat`)

Manually deploying a Lambda update requires multiple steps: zipping the code, uploading it, waiting for AWS to finish processing it, freezing a numbered version, and pointing the live alias to that version. `deploy.bat` automates this entire sequence into a single command:

```
deploy.bat
```

What it does, in order:
1. Deletes any old zip file
2. Re-zips the `lambda/pricewatch` folder
3. Uploads the new code via `aws lambda update-function-code`
4. Waits for AWS to finish applying the update
5. Publishes a new, permanent numbered version (`aws lambda publish-version`)
6. Points the `prod` alias to that new version (`aws lambda update-alias`)
7. Runs a test invoke against `prod` to confirm the deployment works

Because EventBridge always calls the `prod` alias, this script gives a zero-downtime deploy — the live schedule is never interrupted, and a bad deploy can be rolled back by simply pointing the alias back to the previous version number.

---

## 8. Setting this up from scratch (AWS CLI commands used)

```bash
# 1. DynamoDB table
aws dynamodb create-table --table-name crypto-prices \
  --attribute-definitions AttributeName=coin_id,AttributeType=S AttributeName=timestamp,AttributeType=S \
  --key-schema AttributeName=coin_id,KeyType=HASH AttributeName=timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST --region ap-southeast-2

# 2. SNS topic + email subscription
aws sns create-topic --name pricewatch-alerts --region ap-southeast-2
aws sns subscribe --topic-arn <topic-arn> --protocol email --notification-endpoint you@example.com --region ap-southeast-2

# 3. IAM role
aws iam create-role --role-name pricewatch-lambda-role --assume-role-policy-document file://trust-policy.json
aws iam put-role-policy --role-name pricewatch-lambda-role --policy-name pricewatch-permissions --policy-document file://permissions-policy.json

# 4. Lambda function
aws lambda create-function --function-name pricewatch-fetcher --runtime python3.12 \
  --role <role-arn> --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda/pricewatch.zip --timeout 30 --region ap-southeast-2 \
  --environment file://environment.json

# 5. Versioning + alias
aws lambda publish-version --function-name pricewatch-fetcher --region ap-southeast-2
aws lambda create-alias --function-name pricewatch-fetcher --name prod --function-version 1 --region ap-southeast-2

# 6. EventBridge schedule
aws events put-rule --name pricewatch-schedule --schedule-expression "rate(15 minutes)" --region ap-southeast-2
aws lambda add-permission --function-name pricewatch-fetcher --qualifier prod \
  --statement-id pricewatch-eventbridge-prod --action lambda:InvokeFunction \
  --principal events.amazonaws.com --source-arn <rule-arn> --region ap-southeast-2
aws events put-targets --rule pricewatch-schedule --targets file://targets.json --region ap-southeast-2
```

---

## 9. Testing & verification

- **Manual invoke:** `aws lambda invoke --function-name pricewatch-fetcher --region ap-southeast-2 response.json` — runs the function on demand and writes the result to `response.json`.
- **Data check:** `aws dynamodb scan --table-name crypto-prices --region ap-southeast-2` — confirms rows are actually being written, with fresh timestamps appearing every 15 minutes once the schedule is live.
- **Alert check:** lowering `PRICE_THRESHOLD_USD` to a value below the current price (e.g. `1`) and redeploying triggers an immediate email through SNS — a quick way to prove the alerting path works end to end.

---

## 10. Cost

This project is designed to run effectively for free:
- DynamoDB (`PAY_PER_REQUEST`) — negligible at this read/write volume
- Lambda — well within the 1M free monthly invocations (96 invocations/day at a 15-minute schedule)
- SNS — well within the permanent free tier of 1,000 email notifications/month
- EventBridge — scheduled rules have no additional charge at this scale

## 11. Possible future improvements

- Add an **SQS dead-letter queue** so failed records are queryable later, not just logged in an alert email
- Add a **CloudWatch Alarm** on Lambda error rate, separate from the application-level SNS alerts
- Move from manual AWS CLI setup to **Infrastructure as Code** (AWS SAM or Terraform) for one-command, reproducible environment creation
- Replace `deploy.bat` with a **GitHub Actions** workflow, so pushing to `main` deploys automatically
- Add **unit tests** for `transform.py` using `pytest`, with AWS calls mocked via `moto`
- Track more coins, and add a small dashboard (e.g. QuickSight or a simple web page) to visualize price history from DynamoDB

---

## Author

Built by Ankit Vishwakarma as a hands-on project to practice serverless architecture, event-driven design, and safe CI/CD deployment patterns on AWS.
