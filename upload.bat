@echo off
cd /d D:\me\ai107

echo [1/4] 暂存当前源码（已自动忽略 dist/build/密钥/证书/音频缓存等）
git add -A

echo [2/4] 提交
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "[web] update: UI network switch, AI protocol draft, time/timer tools, voice UX"
) else (
    echo 没有需要提交的变更
)

echo [3/4] 获取远端并 rebase 到最新
git fetch origin
if errorlevel 1 (
    echo 获取远端失败，请检查网络或 GitHub 凭据。
    pause
    exit /b 1
)
git rebase origin/codex/asr-demo-unified-understanding
if errorlevel 1 (
    echo rebase 出现冲突，请先解决冲突后再执行 git rebase --continue 和 git push。
    pause
    exit /b 1
)

echo [4/4] 推送
git push origin codex/asr-demo-unified-understanding
if errorlevel 1 (
    echo 推送失败，请检查网络、权限或分支保护规则。
    pause
    exit /b 1
)

echo 上传完成。
pause
