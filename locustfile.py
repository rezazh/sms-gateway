import uuid
import random
import os
from locust import HttpUser, task, between

DEFAULT_API_KEY = "XpDeksFh4e7sgmdLolghBL4f3a6L4TlLrlk5rtWBcUsUUfTjEi2533qK6QY5rdMO"


class SMSGatewayUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        self.api_key = os.environ.get("LOCUST_API_KEY", DEFAULT_API_KEY)

        self.client.headers.update({
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        })

    def _generate_phone(self):
        suffix = random.randint(10000000, 99999999)
        return f"091{suffix}"

    @task(10)
    def send_normal_sms(self):
        request_id = str(uuid.uuid4())
        payload = {
            "recipient": self._generate_phone(),
            "message": f"Load test message {random.randint(1, 1000)}",
            "priority": "normal"
        }

        self.client.post(
            "/api/sms/send/",
            json=payload,
            headers={"X-Request-ID": request_id},
            name="/api/sms/send/ (Normal)"
        )

    @task(3)
    def send_express_sms(self):
        request_id = str(uuid.uuid4())
        payload = {
            "recipient": self._generate_phone(),
            "message": "Urgent OTP Message",
            "priority": "express"
        }

        self.client.post(
            "/api/sms/send/",
            json=payload,
            headers={"X-Request-ID": request_id},
            name="/api/sms/send/ (Express)"
        )

    @task(5)
    def check_balance(self):
        self.client.get("/api/credits/balance/", name="/api/credits/balance/")

    @task(1)
    def check_statistics(self):
        self.client.get("/api/sms/statistics/", name="/api/sms/statistics/")