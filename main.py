import requests
from datetime import datetime

session = requests.Session()

# URLs
BASE_URL = "https://www.stalbanshc.co.uk"
JWT_API_URL = f"{BASE_URL}/api/v2/auth/jwt"
TEAM_SHEET_URL = f"{BASE_URL}/teams/227281/match-centre/1-15844558/lineup"
MATCHES_URL = f"{BASE_URL}/matches"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Referer": "https://www.stalbanshc.co.uk/",
    "Cache-Control": "max-age=0",
    "Upgrade-Insecure-Requests": "1",
    "Content-Type": "application/json"
}

# Step 1: Authenticate to get connect.sid
jwt_payload = {
    "username": "",
    "password": ""
}

#jwt_response = session.post(JWT_API_URL, json=jwt_payload, headers=headers)
#print("JWT Response:", jwt_response.text)
#print("Cookies after auth:", session.cookies.get_dict())

#if jwt_response.status_code == 200:
    # Step 2: Get team sheet
    #team_sheet_response = session.get(TEAM_SHEET_URL, headers=headers)
    #print("\nTeam Sheet Status:", team_sheet_response.status_code)
    #print("Team Sheet Content:", team_sheet_response.text[:500])  # First 500 chars to avoid flooding console

# Get matches data
response = requests.get(MATCHES_URL, headers=headers)
print(f"Response Status: {response.status_code}")

if response.status_code == 200:
    # Create filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"matches_data_{timestamp}.html"
    
    # Save the raw HTML response
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(response.text)
    
    print(f"Data saved to {filename}")
else:
    print(f"Failed to get data: {response.status_code}")
    print(response.text)