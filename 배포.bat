@echo off
cd /d C:\Users\USER\Desktop\artincalendar

echo ================================
echo   ArtInCalendar Deploy Script
echo ================================
echo.

set /p VERSION=Version (ex: 1.2.1) :

echo.
echo [1/4] git add...
git add .

echo [2/4] git commit...
git commit -m "v%VERSION%"

echo [3/4] git push...
git push

echo [4/4] tagging v%VERSION%...
git tag v%VERSION%
git push origin v%VERSION%

echo.
echo ================================
echo   Done! Build started.
echo   Wait 5~10 minutes.
echo ================================
echo.
pause
