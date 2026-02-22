import requests
from requests.auth import HTTPBasicAuth
import os

# 설정 정보 (기존과 동일)
JIRA_BASE_URL = "https://nckorea.atlassian.net"
USER_EMAIL = "cjh22@ncsoft.com"
API_TOKEN = os.environ.get("JIRA_API_TOKEN")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL")

def check_my_boards():
    auth = HTTPBasicAuth(USER_EMAIL, API_TOKEN)
    headers = {"Accept": "application/json"}
    
    # 내 계정이 볼 수 있는 모든 보드 목록을 가져옵니다.
    res = requests.get(f"{JIRA_BASE_URL}/rest/agile/1.0/board", auth=auth, headers=headers)
    boards = res.json().get('values', [])
    
    summary = []
    for b in boards:
        summary.append(f"- [{b['id']}] {b['name']} ({b['type']})")
    
    report = "**🔍 내 계정에서 접근 가능한 보드 목록:**\n\n" + "\n".join(summary)
    requests.post(TEAMS_WEBHOOK_URL, json={"text": report})

if __name__ == "__main__":
    check_my_boards()
