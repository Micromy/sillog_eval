import os
from atlassian import Jira
from bs4 import BeautifulSoup


def get_all_issues(jql: str = "") -> list[dict]:
    jira = Jira(url=os.environ.get("JIRA_URL"),
            username=os.environ.get("JIRA_USERNAME"),
            password=os.environ.get("JIRA_PASSWORD"),
            verify_ssl=False)

    start = 0
    limit = 500
    all_issues: list[dict] = []

    while True:
        result = jira.jql(
            jql,
            start=start,
            limit=limit
        )

        issues = result["issues"]
        all_issues.extend(issues)

        if len(issues) < limit:
            break

        start += limit

    return all_issues


def get_jql_filter(filter_id: str) -> str:
    jira = Jira(url=os.environ.get("JIRA_URL"),
        username=os.environ.get("JIRA_USERNAME"),
        password=os.environ.get("JIRA_PASSWORD"),
        verify_ssl=False)

    filter = jira.get_filter(filter_id)
    return filter["jql"]


def split_jira_sections(description_html: str) -> dict[str, str]:
    soup = BeautifulSoup(description_html, "html.parser")
    sections: dict[str, str] = {"description": "", "checklist": "", "outputs": ""}

    for block in soup.select("div.jefolding"):
        head = block.select_one("div.jefolding_head")
        body = block.select_one("div.jefolding_main")
        if not head or not body:
            continue

        title = head.get_text(strip=True).lower()
        content = body.get_text("\n", strip=True)

        if "description" in title:
            sections["description"] = content
        elif "완료조건" in title or "checklist" in title:
            sections["checklist"] = content
        elif "산출물" in title or "output" in title:
            sections["outputs"] = content

    return sections


def get_sections_by_key(jql: str = "") -> dict[str, dict[str, str]]:
    issues = get_all_issues(jql)
    sections_by_key = {issue['key']: split_jira_sections(issue['fields']['description']) for issue in issues}
    return sections_by_key
