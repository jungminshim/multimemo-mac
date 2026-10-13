#!/bin/bash
# 멀티 메모 맥 앱(.app) 만들기 - 처음 한 번만 실행하면 됩니다.
# 실행: 터미널에서  sh  를 입력하고 한 칸 띄운 뒤 이 파일을 끌어다 놓고 Enter
set -e
cd "$(dirname "$0")"
APP_NAME="멀티 메모"

echo "== 멀티 메모 앱 만들기 =="

# 1) python.org 파이썬(Tk 8.6 포함)이 필요
PY=""
for p in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c "import tkinter, sys; sys.exit(0 if tkinter.TkVersion >= 8.6 else 1)" 2>/dev/null; then
    PY="$p"; break
  fi
done
if [ -z "$PY" ]; then
  echo ""
  echo "⚠ 파이썬이 없거나, 맥 기본 파이썬이라 화면 기능(Tk 8.6)이 없습니다."
  echo "  열리는 페이지에서 'macOS 64-bit universal2 installer'를 받아 설치한 뒤"
  echo "  이 스크립트를 다시 실행해 주세요."
  open "https://www.python.org/downloads/macos/"
  exit 1
fi
echo "파이썬: $($PY --version)"

# 2) 앱 포장 도구 설치 (이 폴더 안 .venv에만 설치됨)
"$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip pyinstaller

# 3) .app 만들기
.venv/bin/pyinstaller --noconfirm --clean --windowed \
  --name "$APP_NAME" --icon icon.icns \
  --osx-bundle-identifier com.multimemo.app \
  multimemo.py

# 4) 응용 프로그램 폴더에 설치
rm -rf "/Applications/$APP_NAME.app"
cp -R "dist/$APP_NAME.app" /Applications/
rm -rf build dist "$APP_NAME.spec"

echo ""
echo "✓ 완료! 응용 프로그램(Launchpad)에서 '$APP_NAME'을 실행하세요."
echo "  메모는  문서/멀티메모  폴더에 메모별 .txt 파일로 저장됩니다."
open "/Applications/$APP_NAME.app"
