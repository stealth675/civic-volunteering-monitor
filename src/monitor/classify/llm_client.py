from __future__ import annotations

import json

from openai import AzureOpenAI, OpenAI


def classify_json(settings, prompt: str) -> dict:
    if settings.openai_provider == "azure":
        client = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
        model = settings.azure_openai_deployment
    else:
        client = OpenAI(api_key=settings.openai_api_key)
        model = settings.openai_model

    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Returner kun JSON."},
            {"role": "user", "content": prompt},
        ],
    )
    content = resp.choices[0].message.content or "{}"
    return json.loads(content)
