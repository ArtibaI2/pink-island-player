@echo off
title Pink Island Audio Player
cd /d "%~dp0"
echo Starting Pink Island Player (Rust Core + iOS Glass UI)...
start "" pythonw "%~dp0player_host.py"
exit
