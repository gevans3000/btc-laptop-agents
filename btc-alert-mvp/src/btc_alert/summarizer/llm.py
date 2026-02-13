import os

import httpx


def synthesize_alert_text(payload: dict) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return (
            f"BTC Alert {payload['symbol']}: {payload['trigger_label']} "
            f"(score={payload['trigger_score']}, momentum={payload['momentum_regime']}, "
            f"24h={payload['price_change_percent']:.2f}%, F&G={payload['fear_greed_value']})."
        )

    prompt = (
        "Write one concise market alert sentence under 35 words using this JSON data: "
        f"{payload}"
    )
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": os.environ.get("BTC_ALERT_LLM_MODEL", "gpt-4o-mini"),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
