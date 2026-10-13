#!/bin/bash
# 앱으로 만들지 않고 바로 실행 (python.org 파이썬 필요)
# 실행: 터미널에서  sh  를 입력하고 한 칸 띄운 뒤 이 파일을 끌어다 놓고 Enter
cd "$(dirname "$0")"
python3 multimemo.py
