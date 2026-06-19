# Caso ruim: credencial hardcoded no código (deveria usar Secret Manager).
api_key = "hardcoded_9f8e7d6c5b4a32100ffee1234"


def call_api():
    return api_key
