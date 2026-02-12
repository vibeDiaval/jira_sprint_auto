import requests
from requests.auth import HTTPBasicAuth
import json
from datetime import datetime, timedelta, timezone

# --- [설정 정보] 기획자님이 전달해주신 실제 데이터 적용 ---
JIRA_BASE_URL = "https://nckorea.atlassian.net"
USER_EMAIL = "cjh22@ncsoft.com"
API_TOKEN = "ATATT3xFfGF0eeQyF7n19OxSVxv1RU-4gpxYey1Wr0LmEJSJdQqnCMcjMY4y6IQGAX9JPBvglCZSkFPwOSywahKuXFT3eZ2sFBheXHvLgXNuq14jI0EAULAwF4i4XtQmvGW-2yHU837dLnV2W6uoj3la_NyMyY4NGcfxDsPv0dHGbiFXmdkUnmA=066EAD73"
BOARD_ID = "3306"
TEAMS_WEBHOOK_URL = "https://default91856527a4464990b48e37ca10f2ee.8d.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/fa1884956055455db362e030f81990ed/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=39ACoUUxHkWSH3cZ11BRS8_jnkVN0udLwAgc2ROU8u0"

def send_teams_report(message, is_success=True):
    """MS Teams로 최종 결과를 보고하는 함수 (Step 5)"""
    headers = {"Content-Type": "application/json"}
    status_title = "🚀 스프린트 활성화 성공" if is_success else "⚠️ 자동화 중단/실패"
    theme_color = "00FF00" if is_success else "FF0000"
    
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
    auth = HTTPBasicAuth(USER_EMAIL, API_TOKEN)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    
    try:
        # Step 1. 미래 스프린트 존재 여부 확인
        sprint_url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{BOARD_ID}/sprint"
        # active와 future 상태의 스프린트만 조회
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
            # 이관할 티켓 수 미리 파악 (완료되지 않은 티켓 조회)
            issue_url = f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{active_id}/issue"
            issues_res = requests.get(issue_url, auth=auth, headers=headers)
            issues = issues_res.json().get('issues', [])
            # statusCategory가 'done'이 아닌 것들 필터링
            incomplete_count = len([i for i in issues if i['fields']['status']['statusCategory']['key'] != 'done'])
            
            # 스프린트 종료 처리
            close_url = f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{active_id}"
            close_payload = {
                "state": "closed",
                "incompleteIssuesDestinationSprintId": target_id
            }
            requests.put(close_url, auth=auth, headers=headers, data=json.dumps(close_payload))

        # Step 3. 새 스프린트 업무 항목 최종 점검
        # 이관 후 새 스프린트의 티켓 수 확인
        check_url = f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{target_id}/issue"
        check_res = requests.get(check_url, auth=auth, headers=headers)
        current_issue_count = check_res.json().get('total', 0)
        
        backlog_added = "N"
        if current_issue_count == 0:
            # 백로그에서 티켓 1개 가져오기
            backlog_url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{BOARD_ID}/backlog"
            backlog_res = requests.get(backlog_url, auth=auth, headers=headers)
            backlog_issues = backlog_res.json().get('issues', [])
            
            if backlog_issues:
                top_issue_key = backlog_issues[0]['key']
                move_url = f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{target_id}/issue"
                move_payload = {"issues": [top_issue_key]}
                requests.post(move_url, auth=auth, headers=headers, data=json.dumps(move_payload))
                backlog_added = f"Y ({top_issue_key})"
            else:
                send_teams_report("자동화 중단: 백로그에 업무가 없어 시작이 불가능합니다.", False)
                return

        # Step 4. 새 스프린트 활성화 (시간 설정 반영)
        now = datetime.now(timezone(timedelta(hours=9))) # KST 기준
        start_date_str = now.strftime('%Y-%m-%dT%H:%M:%S.000+0900')
        
        # 기존에 설정된 종료일이 있는지 확인
        existing_end_date = target_sprint.get('endDate')
        if not existing_end_date:
            # 없으면 1주일 뒤로 설정
            end_date = now + timedelta(days=7)
            end_date_str = end_date.strftime('%Y-%m-%dT%H:%M:%S.000+0900')
        else:
            end_date_str = existing_end_date

        activate_url = f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{target_id}"
        activate_payload = {
            "state": "active",
            "startDate": start_date_str,
            "endDate": end_date_str
        }
        final_res = requests.put(activate_url, auth=auth, headers=headers, data=json.dumps(activate_payload))
        
        # Step 5. 결과 보고
        if final_res.status_code in [200, 204]:
            msg = f"스프린트 [{target_name}] 활성화 완료!\n- 이관 티켓: {incomplete_count}개\n- 백로그 추가: {backlog_added}"
            send_teams_report(msg, True)
        else:
            send_teams_report(f"자동화 중단: 활성화 단계 오류 (Jira 응답: {final_res.text})", False)

    except Exception as e:
        send_teams_report(f"자동화 실행 중 예상치 못한 에러 발생: {str(e)}", False)

if __name__ == "__main__":
    run_jira_automation()