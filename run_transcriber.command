#!/bin/bash
python3 "$(dirname "$0")/transcriber_pyside6.py"
read -n 1 -s -r -p "Нажмите любую клавишу для выхода..."
