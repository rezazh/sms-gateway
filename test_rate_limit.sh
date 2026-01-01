#!/bin/bash

API_KEY="YOUR_API_KEY_HERE"

echo "Testing rate limiting..."
echo "Sending 105 requests (limit is 100 per minute)"
echo ""

for i in {1..105}
do
    response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X GET \
        http://127.0.0.1:8000/api/credits/balance/ \
        -H "X-API-Key: $API_KEY")

    http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)

    if [ "$http_code" = "429" ]; then
        echo "Request $i: Rate limit exceeded (429)"
        break
    else
        echo "Request $i: Success ($http_code)"
    fi
done