#!/bin/bash
# sync_skills_to_trae.sh
# 把 ~/.agents/skills/ 下所有 skill 软链到 Trae IDE 的内置 skill 目录
# 用法: ./sync_skills_to_trae.sh
set -e

SRC_DIR="$HOME/.agents/skills"
DEST_DIRS=(
  "/data/user/builtin/global/skills"
  "/data/user/builtin/code/default/skills"
  "/data/user/builtin/work/default/skills"
)

if [ ! -d "$SRC_DIR" ]; then
  echo "❌ 源目录不存在: $SRC_DIR"
  exit 1
fi

count=0
for skill_dir in "$SRC_DIR"/*/; do
  [ -d "$skill_dir" ] || continue
  skill_name=$(basename "$skill_dir")
  [ -f "$skill_dir/SKILL.md" ] || { echo "⏭️  跳过 $skill_name (无 SKILL.md)"; continue; }

  for dest in "${DEST_DIRS[@]}"; do
    [ -d "$dest" ] || continue
    ln -sfn "$skill_dir" "$dest/$skill_name"
    echo "  ✓ $dest/$skill_name → $skill_dir"
  done
  count=$((count + 1))
done

echo
echo "✅ 同步完成:$count 个 skill"
echo "⚠️  请重启 Trae IDE 以加载新 skill"
