import requests

url = "http://127.0.0.1:8000/api/data/"

data = {
    "soil": 450,
    "pump": 1,
    "mode": 1
}

r = requests.post(url, json=data)

print(r.text)