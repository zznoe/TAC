#!/bin/bash
# TAC 仓库:完成 main 设为默认 + 分支保护
# 用法: TOKEN=ghp_xxx ./finish_main_setup.sh
set -e

: "${TOKEN:?请先设置环境变量 TOKEN=<有 Administration 权限的 PAT>}"
REPO="zznoe/TAC"
BRANCH="main"
API="https://api.github.com/repos/$REPO"

echo "=== 1. 切换默认分支为 main ==="
curl -sS -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{"default_branch":"main"}' \
  "$API" | python -c "import json,sys; d=json.load(sys.stdin); print('default_branch =', d.get('default_branch', d))"

echo
echo "=== 2. 给 main 加分支保护 ==="
curl -sS -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{
    "required_status_checks": null,
    "enforce_admins": true,
    "required_pull_request_reviews": {
      "dismiss_stale_reviews": true,
      "require_code_owner_reviews": false,
      "required_approving_review_count": 1
    },
    "restrictions": null,
    "required_linear_history": true,
    "allow_force_pushes": false,
    "allow_deletions": false,
    "required_conversation_resolution": true
  }' \
  "$API/branches/$BRANCH/protection" \
  -w "\nHTTP %{http_code}\n"

echo
echo "=== 3. 验证 ==="
echo "[3.1] 默认分支:"
curl -sS -H "Authorization: Bearer $TOKEN" "$API" \
  | python -c "import json,sys; d=json.load(sys.stdin); print('  default_branch =', d.get('default_branch'))"

echo "[3.2] main 保护状态:"
curl -sS -H "Authorization: Bearer $TOKEN" "$API/branches/$BRANCH" \
  | python -c "import json,sys; d=json.load(sys.stdin); print('  protected =', d.get('protected'))"

echo "[3.3] 保护规则摘要:"
curl -sS -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  "$API/branches/$BRANCH/protection" \
  | python -c "
import json, sys
d = json.load(sys.stdin)
print('  enforce_admins       =', d.get('enforce_admins'))
print('  required_linear_history =', d.get('required_linear_history'))
print('  allow_force_pushes   =', d.get('allow_force_pushes'))
print('  allow_deletions      =', d.get('allow_deletions'))
print('  required_conversation_resolution =', d.get('required_conversation_resolution'))
pr = d.get('required_pull_request_reviews', {})
print('  required_approving_review_count  =', pr.get('required_approving_review_count'))
print('  dismiss_stale_reviews =', pr.get('dismiss_stale_reviews'))
"
