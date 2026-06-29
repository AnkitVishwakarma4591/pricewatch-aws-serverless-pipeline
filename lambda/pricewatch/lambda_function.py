import json
import os
import urllib.request
from decimal import Decimal
from datetime import datetime, timezone
import boto3
from transform import validate_price, crossed_threshold

DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "crypto-prices")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
COINS = os.environ.get("COINS", "bitcoin,ethereum").split(",")
PRICE_THRESHOLD_USD = Decimal(os.environ.get("PRICE_THRESHOLD_USD", "1000000"))

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids={}&vs_currencies=usd"

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")

def lambda_handler(event, context):
    table = dynamodb.Table(DYNAMODB_TABLE)
    timestamp = datetime.now(timezone.utc).isoformat()

    url = COINGECKO_URL.format(",".join(COINS))
    with urllib.request.urlopen(url, timeout=10) as response:
        price_data = json.loads(response.read().decode())

    saved = []
    errors = []

    for coin_id in COINS:
        try:
            price = validate_price(coin_id, price_data)
        except ValueError as e:
            errors.append(str(e))
            continue

        table.put_item(Item={
            "coin_id": coin_id,
            "timestamp": timestamp,
            "price_usd": price
        })
        saved.append({"coin_id": coin_id, "price_usd": str(price)})

        if crossed_threshold(price, PRICE_THRESHOLD_USD) and SNS_TOPIC_ARN:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=f"PriceWatch alert: {coin_id}",
                Message=f"{coin_id} price is now ${price} (threshold ${PRICE_THRESHOLD_USD})"
            )

    if errors and SNS_TOPIC_ARN:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="PriceWatch: some coins failed validation",
            Message="\n".join(errors)
        )

    return {
        "statusCode": 200,
        "body": json.dumps({"saved": saved, "errors": errors})
    }