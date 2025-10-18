# import requests

# webhook_url = "https://discord.com/api/webhooks/1428324798316150864/pYw3aUmm1DZ9td7Lc2KJLoJUHIvQXnQkXuD5x8Ng2e35tMG5HIeOCQcNWWOMGgGhPp9a"

# data = {
#     "embeds": [
#         {
#             "title": "Altaria Vs.​ ​ ​​★ Farfetch’d",  # Paste exact title here
#             "description": "Test embed",
#             "color": 0xFF0000,
#         }
#     ]
# }

# requests.post(webhook_url, json=data)


import re

SHINY_PATTERN = re.compile(r"Vs\.[\s\u200B]*\u2605", re.UNICODE)

# Test with your embed title
title = "moolerb (Breloom) Vs.​ ​ ​​★ Zeraora"

if SHINY_PATTERN.search(title):
    print("✅ MATCH! Shiny will be detected!")
else:
    print("❌ NO MATCH")

# Result: ✅ MATCH! Shiny will be detected!
