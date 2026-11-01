@echo off
echo === Site AI Creation Editor: first-time setup ===
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
if not exist .env copy .env.example .env
echo.
echo Setup finished. Open the file ".env" in Notepad and paste your free Gemini key
echo after GEMINI_API_KEY= (optional but gives much better scripts). Then run run.bat
pause
