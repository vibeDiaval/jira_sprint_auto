import requests
from requests.auth import HTTPBasicAuth
import os
import json

# 설정 정보
JIRA_BASE_URL = "https://nckorea.atlassian.net"
USER_EMAIL = "cjh22@ncsoft.com"
API_TOKEN = os.environ.get("JIRA_API_TOKEN")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL")

def check_my_boards():
    # 1. 환경 변수 확인 로그 (보안을 위해 일부만 출력)
    print(f"--- 환경 변수 체크 ---")
    print(f"EMAIL: {USER_EMAIL}")
    print(f"TOKEN 존재 여부: {'Yes' if API_TOKEN else 'No'}")
    print(f"WEBHOOK 존재 여부: {'Yes' if TEAMS_WEBHOOK_URL else 'No'}")

    auth = HTTPBasicAuth(USER_EMAIL, API_TOKEN)
    headers = {"Accept": "application/json"}
    
    try:
        # 2. 지라 API 호출 및 상태 코드 확인
        print(f"\n--- 지라 API 호출 시작 ---")
        res = requests.get(f"{JIRA_BASE_URL}/rest/agile/1.0/board", auth=auth, headers=headers)
        print(f"Jira 응답 상태 코드: {res.status_code}")
        
        if res.status_code != 200:
            print(f"에러 발생! 응답 내용: {res.text}")
            return

        boards = res.json().get('values', [])
        print(f"발견된 보드 수: {len(boards)}")

        summary = []
        for b in boards:
            info = f"- [{b['id']}] {b['name']} ({b['type']})"
            print(info) # 깃허브 로그에 출력
            summary.append(info)
        
        # 3. 팀즈 전송 시도
        if summary:
            report = "**🔍 내 계정에서 접근 가능한 보드 목록:**\n\n" + "\n".join(summary)
            teams_res = requests.post(TEAMS_WEBHOOK_URL, json={"text": report})
            print(f"팀즈 전송 결과 상태 코드: {teams_res.status_code}")
        else:
            print("발견된 보드가 없어 팀즈 메시지를 보내지 않았습니다.")

    except Exception as e:
        print(f"코드 실행 중 시스템 오류 발생: {str(e)}")

if __name__ == "__main__":
    check_my_boards()
