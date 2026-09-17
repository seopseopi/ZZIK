#!/usr/bin/env python3
"""Render teammate prompts from the reviewed, versioned work plan."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def bullets(items):
    return '\n'.join(f'- {item}' for item in items)


def render(plan):
    roles = {role['id']: role for role in plan['roles']}
    preamble = (
        '> `plan.json`에서 생성한 프롬프트입니다. 수정 후 '
        '`python scripts/render_hackathon_prompts.py`를 실행하세요.\n\n'
        '아래 지시를 작업 프롬프트로 사용한다. 먼저 저장소의 `AGENTS.md`, '
        '`docs/hackathon/COMMON.md`, `docs/hackathon/OWNERSHIP.md`, '
        '`docs/API_CONTRACT.md`, `contracts/README.md`, `docs/hackathon/PR_WORKFLOW.md`를 읽는다.\n'
    )
    output = {}
    for role in plan['roles']:
        assigned = [task for task in plan['tasks'] if task['owner'] == role['id']]
        supporting = [task['id'] for task in plan['tasks'] if role['id'] in task['collaborators']]
        output[role['prompt']] = (
            f'# 담당 {role["id"]}: {role["title"]}\n\n{preamble}\n'
            f'너는 ZZIK 팀의 {role["id"]}번 담당이다. 아래 역할 범위에서 현재 코드를 먼저 '
            '검토하고, 지정된 M 작업을 하나씩 진행한다. 모든 M을 한 번에 다시 구현하지 않는다.\n\n'
            '## 책임\n\n' + bullets(role['instructions']) + '\n\n'
            '## 확인할 파일\n\n' + bullets(f'`{path}`' for path in role['files']) + '\n\n'
            '## 주관 작업\n\n' + bullets(
                f'[{task["id"]} {task["title"]}](../tasks/{task["id"]}.md) · {task["priority"]}'
                for task in assigned
            ) + '\n\n'
            '## 협업 작업\n\n' + (', '.join(supporting) or '없음') + '\n\n'
            '공유 파일의 통합 담당은 `OWNERSHIP.md`가 우선이다. 작업 프롬프트의 파일 목록이 '
            '독점 수정 권한을 뜻하지 않는다. 필요한 계약 변경을 의존 PR로 명시하고, '
            '기능·검사 결과·미검증 조건을 다음 담당에게 전달한다.\n'
        )
    for task in plan['tasks']:
        commands = []
        for command in task['validation']:
            command = command.split(' (')[0]
            commands.append(command)
        output[task['prompt']] = (
            f'# {task["id"]} · {task["title"]}\n\n{preamble}\n'
            f'- 주관: {task["owner"]}번 {roles[task["owner"]]["title"]}\n'
            f'- 협업: {", ".join(str(value) + "번" for value in task["collaborators"]) or "없음"}\n'
            f'- 우선순위: {task["priority"]} · 원문 단계: {task["phase"]}\n'
            f'- 선행 작업: {", ".join(task["depends_on"]) or "공통 계약 확정"}\n\n'
            '## 목표\n\n' + task['goal'] + '\n\n'
            '## 출발 상태\n\n' + task['current_status'] + '. '
            '이 상태는 계획 작성 시점의 기준이며 이번 작업의 완료 증거가 아니다. '
            '기존 구현과 테스트를 읽고 부족한 부분만 변경한다.\n\n'
            '## 확인할 파일\n\n' + bullets(f'`{path}`' for path in task['files']) + '\n\n'
            '## 연결 계약\n\n' + (bullets(f'`{endpoint}`' for endpoint in task['endpoints']) or
            'HTTP 경로·배포 환경·스토리지·worker 실행 계약을 확인한다.') + '\n\n'
            '요청·오류는 `contracts/openapi.json`, 상세 응답 의미는 `docs/API_CONTRACT.md`, '
            'Python 호출 경계는 `contracts/python-interfaces.json`을 따른다. '
            '프론트 타입은 OpenAPI에서 생성한다. 계약 변경 시 스냅샷과 타입을 함께 갱신하고 `npm --prefix frontend run types:check` 및 실제 응답 검사를 수행한다.\n\n'
            '## 진행 순서\n\n'
            '1. `git status`와 선행 PR을 확인하고 M 번호가 있는 작업 브랜치를 사용한다.\n'
            '2. 현재 기능을 재현하고 완료 조건별로 구현됨/부족함/외부 검증 필요를 나눈다.\n'
            '3. 주관 범위의 변경을 구현한다. 공유 API·DB·화면 변경은 통합 담당과 조정한다.\n'
            '4. 아래 검사를 실행하고 정상·실패 경로를 확인한다. 외부 검증은 샘플로 대체하지 않는다.\n'
            '5. 기능 단위 커밋과 PR에 계약 변경·검사 결과·남은 조건을 기록한다.\n\n'
            '## 완료 조건\n\n' + bullets(f'[ ] {item}' for item in task['acceptance']) + '\n\n'
            '## 검증\n\n'
            '`TEST_DATABASE_URL`은 전용 `_test` DB, `ZZIK_E2E_DATABASE_URL`은 로컬 전용 '
            '`_e2e` DB를 지정한다. 설치와 예시는 [조립 가이드](../ASSEMBLY.md)를 따른다.\n\n'
            '```bash\n' + '\n'.join(dict.fromkeys([*commands, '.venv/bin/python scripts/check_harness.py'])) + '\n```\n\n'
            '## 외부 검증\n\n' + (task['external_evidence'] or
            '이 기능을 AWS에서 완료했다고 보고하려면 배포 커밋과 실제 서버 시나리오 결과를 별도로 남긴다.') + '\n\n'
            '## 인계 결과\n\n'
            'PR 링크, 변경 파일, API/DB 변경 여부, 실행한 검사와 결과, 재현 방법, '
            '다음 담당이 해결해야 할 조건을 짧게 보고한다.\n'
        )
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    plan = json.loads((ROOT / 'docs/hackathon/plan.json').read_text())
    stale = []
    for path, contents in render(plan).items():
        destination = ROOT / path
        if args.check:
            if not destination.exists() or destination.read_text() != contents:
                stale.append(path)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(contents)
    if stale:
        raise SystemExit('Regenerate prompts with scripts/render_hackathon_prompts.py: ' + ', '.join(stale))
    print('Prompt files match plan.json.' if args.check else 'Generated five role prompts and seventeen task prompts.')


if __name__ == '__main__':
    main()
