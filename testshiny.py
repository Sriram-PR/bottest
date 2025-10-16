import requests

webhook_url = "https://discord.com/api/webhooks/1428324798316150864/pYw3aUmm1DZ9td7Lc2KJLoJUHIvQXnQkXuD5x8Ng2e35tMG5HIeOCQcNWWOMGgGhPp9a"

data = {
    "embeds": [
        {
            "title": "Altaria Vs.​ ​ ​​★ Farfetch’d",  # Paste exact title here
            "description": "Test embed",
            "color": 0xFF0000,
        }
    ]
}

requests.post(webhook_url, json=data)
