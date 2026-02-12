import requests
from requests.auth import HTTPBasicAuth
import json
import os
from datetime import datetime, timedelta, timezone

# --- [설정 정보] 깃허브 금고(Secrets) 환경 변수 사용 ---
JIRA_BASE_URL = "https://nckorea.atlassian.net"
USER_EMAIL = "cjh22@ncsoft.com"
BOARD_ID = "3306"

# GitHub Secrets에 등록한 이름을 그대로 가져옵니다.
API_TOKEN = os.environ.get("JIRA_API_TOKEN")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL")
# ----------------------------------------------------

def send_teams_report(message, is_success=True):
    """MS Teams로 최종 결과를 보고하는 함수 (Step 5)"""
    headers = {"Content-Type": "application/json"}
    status_title = "🚀 스프린트 활성화 성공" if is_success else "⚠️ 자동화 중단/실패"
    
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "body": [
                    {"type": "TextBlock", "text": status_title, "weight": "Bolder", "size": "Large"},
                    {"type": "TextBlock", "text": message, "wrap": True}
                ],
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "version": "1.0"
            }
        }]
    }
    requests.post(TEAMS_WEBHOOK_URL, data=json.dumps(payload), headers=headers)

def run_jira_automation():
    if not API_TOKEN or not TEAMS_WEBHOOK_URL:
        print("에러: GitHub Secrets 설정(JIRA_API_TOKEN 또는 TEAMS_WEBHOOK_URL)을 확인해주세요.")
        return

    auth = HTTPBasicAuth(USER_EMAIL, API_TOKEN)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    
    try:
        # Step 1. 미래 스프린트 존재 여부 확인
        sprint_url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{BOARD_ID}/sprint"
        params = {"state": "active,future"}
        res = requests.get(sprint_url, auth=auth, headers=headers, params=params)
        sprints = res.json().get('values', [])
        
        active_sprints = [s for s in sprints if s['state'] == 'active']
        future_sprints = [s for s in sprints if s['state'] == 'future']
        
        if not future_sprints:
            send_teams_report("예약된 미래 스프린트가 없어 자동화를 중단합니다. 스프린트를 생성해 주세요!", False)
            return
            
        target_sprint = future_sprints[0]
        target_id = target_sprint['id']
        target_name = target_sprint['name']

        # Step 2. 기존 스프린트 종료 및 티켓 이관
        incomplete_count = 0
        if active_sprints:
            active_id = active_sprints[0]['id']
            issue_url = f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{active_id}/issue"
            issues_res = requests.get(issue_url, auth=auth, headers=headers)
            issues = issues_res.json().get('issues', [])
            incomplete_count = len([i for i in issues if i['fields']['status']['statusCategory']['key'] != 'done'])
            
            close_url = f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{active_id}"
            close_payload = {"state": "closed", "incompleteIssuesDestinationSprintId": target_id}
            requests.put(close_url, auth=auth, headers=headers, data=json.dumps(close_payload))

        # Step 3. 새 스프린트 업무 항목 최종 점검
        check_url = f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{target_id}/issue"
        check_res = requests.get(check_url, auth=auth, headers=headers)
        current_issue_count = check_res.json().get('total', 0)
        
        backlog_added = "N"
        if current_issue_count == 0:
            back_url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{BOARD_ID}/backlog"
            back_res = requests.get(back_url, auth=auth, headers=headers)
            back_issues = back_res.json().get('issues', [])
            
            if back_issues:
                top_issue_key = back_issues[0]['key']
                move_url = f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{target_id}/issue"
                move_payload = {"issues": [top_issue_key]}
                requests.post(move_url, auth=auth, headers=headers, data=json.dumps(move_payload))
                backlog_added = f"Y ({top_issue_key})"
            else:
                send_teams_report("자동화 중단: 백로그에 업무가 없어 시작이 불가능합니다.", False)
                return

        # Step 4. 새 스프린트 활성화 (시간 설정 반영)
        now = datetime.now(timezone(timedelta(hours=9)))
        start_date_str = now.strftime('%Y-%m-%dT%H:%M:%S.000+0900')
        
        existing_end_date = target_sprint.get('endDate')
        end_date_str = existing_end_date if existing_end_date else (now + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%S.000+0900')

        activate_url = f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{target_id}"
        activate_payload = {"state": "active", "startDate": start_date_str, "endDate": end_date_str}
        final_res = requests.put(activate_url, auth=auth, headers=headers, data=json.dumps(activate_payload))
        
        # Step 5. 결과 보고
        if final_res.status_code in [200, 204]:
            msg = f"스프린트 [{target_name}] 활성화 완료!\n- 이관 티켓: {incomplete_count}개\n- 백로그 추가: {backlog_added}"
            send_teams_report(msg, True)
        else:
            send_teams_report(f"자동화 중단: 활성화 단계 오류 (Jira 응답: {final_res.text})", False)

    except Exception as e:
        send_teams_report(f"실행 중 에러 발생: {str(e)}", False)

if __name__ == "__main__":
    run_jira_automation()
