import requests
from requests.auth import HTTPBasicAuth
import json
import os
from datetime import datetime, timedelta, timezone

# --- [설정 정보] ---
JIRA_BASE_URL = "https://nckorea.atlassian.net"
USER_EMAIL = "cjh22@ncsoft.com"
BOARD_ID = "3306"
API_TOKEN = os.environ.get("JIRA_API_TOKEN")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL")

def send_teams_report(message, is_success=True):
    headers = {"Content-Type": "application/json"}
    status_title = "🚀 스프린트 활성화 성공" if is_success else "⚠️ 자동화 중단/실패"
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "body": [{"type": "TextBlock", "text": status_title, "weight": "Bolder", "size": "Large"},
                         {"type": "TextBlock", "text": message, "wrap": True}],
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "version": "1.0"
            }
        }]
    }
    requests.post(TEAMS_WEBHOOK_URL, data=json.dumps(payload), headers=headers)

def run_jira_automation():
    auth = HTTPBasicAuth(USER_EMAIL, API_TOKEN)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    
    try:
        # [Step 1] 미래 스프린트 찾기 (더 강력한 검색)
        # 검색 필터를 제거하고 보드의 모든 스프린트를 가져와서 수동으로 필터링합니다.
        sprint_res = requests.get(f"{JIRA_BASE_URL}/rest/agile/1.0/board/{BOARD_ID}/sprint", auth=auth, headers=headers)
        all_sprints = sprint_res.json().get('values', [])
        
        active_sprints = [s for s in all_sprints if s['state'] == 'active']
        # 'future' 상태인 것 중 가장 먼저 생성된 것을 타겟으로 잡습니다.
        future_sprints = [s for s in all_sprints if s['state'] == 'future']
        
        if not future_sprints:
            send_teams_report("보드에서 '시작 전(Future)' 상태인 스프린트를 찾을 수 없습니다. 스프린트가 생성되어 있는지 확인해주세요.", False)
            return
            
        target_sprint = future_sprints[0]
        target_id = target_sprint['id']

        # [Step 2] 기존 스프린트 종료 및 티켓 이관
        incomplete_count = 0
        if active_sprints:
            active_id = active_sprints[0]['id']
            # 미완료 티켓 수 미리 확인
            issues_res = requests.get(f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{active_id}/issue", auth=auth, headers=headers)
            issues = issues_res.json().get('issues', [])
            incomplete_count = len([i for i in issues if i['fields']['status']['statusCategory']['key'] != 'done'])
            
            # 종료 및 이관 (이 시점에서 미래 스프린트로 티켓이 넘어갑니다)
            close_payload = {"state": "closed", "incompleteIssuesDestinationSprintId": target_id}
            requests.put(f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{active_id}", auth=auth, headers=headers, data=json.dumps(close_payload))

        # [Step 3] 새 스프린트 업무 항목 점검 (이관 후에도 0개면 백로그 투입)
        check_res = requests.get(f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{target_id}/issue", auth=auth, headers=headers)
        current_issue_count = check_res.json().get('total', 0)
        
        backlog_added = "N"
        if current_issue_count == 0:
            backlog_res = requests.get(f"{JIRA_BASE_URL}/rest/agile/1.0/board/{BOARD_ID}/backlog", auth=auth, headers=headers)
            backlog_issues = backlog_res.json().get('issues', [])
            if backlog_issues:
                top_issue_key = backlog_issues[0]['key']
                requests.post(f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{target_id}/issue", 
                              auth=auth, headers=headers, data=json.dumps({"issues": [top_issue_key]}))
                backlog_added = f"Y ({top_issue_key})"
            else:
                send_teams_report("이관할 티켓도, 백로그 업무도 없어 스프린트를 시작할 수 없습니다.", False)
                return

        # [Step 4] 새 스프린트 활성화
        now = datetime.now(timezone(timedelta(hours=9)))
        start_date_str = now.strftime('%Y-%m-%dT%H:%M:%S.000+0900')
        end_date_str = target_sprint.get('endDate', (now + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%S.000+0900'))

        activate_res = requests.put(f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{target_id}", 
                                    auth=auth, headers=headers, 
                                    data=json.dumps({"state": "active", "startDate": start_date_str, "endDate": end_date_str}))
        
        # [Step 5] 결과 보고
        if activate_res.status_code in [200, 204]:
            send_teams_report(f"스프린트 [{target_sprint['name']}] 활성화 완료!\n- 이관 티켓: {incomplete_count}개\n- 백로그 추가: {backlog_added}")
        else:
            send_teams_report(f"활성화 실패: {activate_res.text}", False)

    except Exception as e:
        send_teams_report(f"에러 발생: {str(e)}", False)

if __name__ == "__main__":
    run_jira_automation()
