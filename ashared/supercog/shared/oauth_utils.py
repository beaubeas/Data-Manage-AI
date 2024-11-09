import requests

def salesforce_refresh_token(opts: dict, is_sandbox: bool) -> dict:
    data = {
        "grant_type": "refresh_token",
        "client_id": opts["client_id"],
        "client_secret": opts["client_secret"],
        "refresh_token": opts["refresh_token"],
    }
    url = opts["instance_url"] + "/services/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    base = "https://login.salesforce.com/"
    if is_sandbox:
        base = "https://test.salesforce.com/"
    r = requests.post(
        base + "services/oauth2/token",
        data=data,
        headers=headers
    )
    return r.json()

def google_refresh_token(opts: dict) -> dict:
    url = "https://oauth2.googleapis.com/token"
    
    data = {
        "client_id": opts["client_id"],
        "client_secret": opts["client_secret"],
        "refresh_token": opts["refresh_token"],
        "grant_type": "refresh_token"
    }

    try:
        r = requests.post(url, data=data)
        return r.json()
    except Exception as e:
        print(e)
        return {}
