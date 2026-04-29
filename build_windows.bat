@echo off
setlocal

REM Build one-folder app so output is dist\VideoTranslatorPro\VideoTranslatorPro.exe
pyinstaller ^
  --noconfirm ^
  --windowed ^
  --name VideoTranslatorPro ^
  --onedir ^
  --add-data "src;src" ^
  --add-data "assets;assets" ^
  --add-data "fonts;fonts" ^
  app.py

echo.
echo Build complete.
echo Executable: dist\VideoTranslatorPro\VideoTranslatorPro.exe
echo.
echo NOTE:
echo - Do NOT bundle large AI models into EXE.
echo - Download/select models at first run into models\ folder.

endlocal
